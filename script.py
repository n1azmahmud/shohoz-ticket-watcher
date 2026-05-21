import re
import time
import requests
import logging
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# ─────────────────────────────────────────────
#  CONFIGURATION — edit this section
# ─────────────────────────────────────────────

CONFIG = {
    # Your unique ntfy.sh topic — must match exactly what you subscribed to in the ntfy app
    "ntfy_topic": "shohoz_alerts_din-to-dhk",

    # Route details
    "from_city": "Dinajpur",
    "to_city":   "Dhaka",
    "date":      "01-Jun-2026",   # Format: DD-Mon-YYYY  e.g. 15-Jun-2026

    # Preferred bus names (case-insensitive partial match)
    # Notification fires if ANY of these appear in the results
    "preferred_buses": [
        "Shyamoli",
        "Nabil",
    ],

    # Preferred departure time window (24h format). Leave empty strings to match any time.
    # NOTE: if time_to is "00:00" or "24:00" it means end of day (midnight)
    # Example: "20:00" to "00:00" means evening/night buses
    "time_from": "18:00",
    "time_to":   "00:00",

    # How often to check, in seconds (default: 5 minutes)
    "check_interval_seconds": 10,

    # Stop watching after this many hours (0 = run forever)
    "stop_after_hours": 0,

    # Set to True to dump page text on each check — helps debug if buses aren't detected
    "debug": False,
}

# ─────────────────────────────────────────────
#  END OF CONFIGURATION
# ─────────────────────────────────────────────

logging.basicConfig(
    level=logging.DEBUG if CONFIG["debug"] else logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("shohoz_watcher")


def build_url():
    return (
        "https://www.shohoz.com/bus-tickets/booking/bus/search"
        f"?fromcity={CONFIG['from_city']}"
        f"&tocity={CONFIG['to_city']}"
        f"&doj={CONFIG['date']}"
        f"&dor="
    )


def send_notification(title: str, message: str, url: str = ""):
    """Send a push notification via ntfy.sh — emoji-safe."""
    topic = CONFIG["ntfy_topic"]
    try:
        # Encode headers as bytes to avoid latin-1 codec errors on Windows
        headers = {
            "Title":    title.encode("utf-8"),
            "Priority": b"high",
            "Tags":     b"rotating_light,bus",
        }
        if url:
            headers["Click"]   = url.encode("utf-8")
            headers["Actions"] = f"view, Book Now, {url}".encode("utf-8")

        resp = requests.post(
            f"https://ntfy.sh/{topic}",
            data=message.encode("utf-8"),
            headers=headers,
            timeout=10,
        )
        if resp.status_code == 200:
            log.info(f"Notification sent OK: {title}")
        else:
            log.warning(f"ntfy returned {resp.status_code}: {resp.text}")
    except Exception as e:
        log.error(f"Failed to send notification: {e}")


def parse_time_to_minutes(t_str: str):
    """Parse HH:MM or HH:MM AM/PM to minutes since midnight. 00:00 treated as 1440 (end of day)."""
    if not t_str:
        return None
    try:
        t_str = t_str.strip()
        m12 = re.match(r"(\d{1,2}):(\d{2})\s*(AM|PM)", t_str, re.IGNORECASE)
        if m12:
            h, m, ampm = int(m12.group(1)), int(m12.group(2)), m12.group(3).upper()
            if ampm == "PM" and h != 12:
                h += 12
            if ampm == "AM" and h == 12:
                h = 0
            return h * 60 + m
        m24 = re.match(r"(\d{1,2}):(\d{2})", t_str)
        if m24:
            h, m = int(m24.group(1)), int(m24.group(2))
            # Treat 00:00 as end-of-day (1440) when used as time_to
            return h * 60 + m
    except Exception:
        pass
    return None


def time_in_window(departure_time_str: str) -> bool:
    """Return True if departure falls within the configured time window."""
    t_from_str = CONFIG["time_from"].strip()
    t_to_str   = CONFIG["time_to"].strip()

    # No filter configured
    if not t_from_str and not t_to_str:
        return True

    dep_min = parse_time_to_minutes(departure_time_str)
    if dep_min is None:
        return True  # can't parse → let it through

    from_min = parse_time_to_minutes(t_from_str) if t_from_str else 0

    # "00:00" as time_to means midnight / end-of-day = 1440
    if t_to_str in ("00:00", "24:00"):
        to_min = 1440
    else:
        to_min = parse_time_to_minutes(t_to_str) if t_to_str else 1439

    # Handle overnight windows e.g. 20:00 → 00:00 (1200 → 1440)
    if from_min <= to_min:
        return from_min <= dep_min <= to_min
    else:
        # Wraps midnight: e.g. 22:00 → 02:00
        return dep_min >= from_min or dep_min <= to_min


def scrape_buses(page) -> list[dict]:
    """
    Load the Shohoz search page and extract bus listings.
    Works by waiting for the React app to render, then scanning
    the page with multiple selector strategies + a full-text fallback.
    """
    url = build_url()
    log.info(f"Fetching: {url}")

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=40000)
    except PlaywrightTimeout:
        log.warning("Page load timed out — will retry next cycle")
        return []

    # Wait for React to finish rendering (Shohoz is a SPA)
    page.wait_for_timeout(6000)

    if CONFIG["debug"]:
        try:
            body_text = page.inner_text("body")
            log.debug(f"--- PAGE TEXT SAMPLE (first 2000 chars) ---\n{body_text[:2000]}\n---")
        except Exception:
            pass

    buses = []

    # ── Strategy 1: Shohoz bus card selectors (try many variants) ─────────
    # The real class names seen on Shohoz as of 2025-2026:
    CARD_SELECTORS = [
        "div.single-bus-parent",
        "div[class*='single-bus']",
        "div[class*='bus-card']",
        "div[class*='busCard']",
        "div[class*='bus-item']",
        "div[class*='busItem']",
        "div[class*='trip-item']",
        "div[class*='tripItem']",
        "div[class*='coach-item']",
        "div[class*='result-item']",
        "div[class*='BusItem']",
        "div[class*='BusCard']",
    ]

    cards = []
    for sel in CARD_SELECTORS:
        try:
            found = page.query_selector_all(sel)
            if found:
                log.info(f"  Selector '{sel}' matched {len(found)} card(s)")
                cards = found
                break
        except Exception:
            continue

    if cards:
        for card in cards:
            try:
                text  = card.inner_text()
                lines = [l.strip() for l in text.splitlines() if l.strip()]
                if not lines:
                    continue

                bus_info = {
                    "name":      lines[0],
                    "departure": "",
                    "arrival":   "",
                    "fare":      "",
                    "seats":     "",
                }

                # Extract times like "09:30 AM" or "21:30"
                times = re.findall(r"\d{1,2}:\d{2}\s*(?:AM|PM)?", text)
                if len(times) >= 2:
                    bus_info["departure"] = times[0].strip()
                    bus_info["arrival"]   = times[1].strip()
                elif times:
                    bus_info["departure"] = times[0].strip()

                fare = re.search(r"(?:BDT|Tk\.?|TK|৳)\s*[\d,]+", text, re.IGNORECASE)
                if fare:
                    bus_info["fare"] = fare.group(0)

                seats = re.search(r"(\d+)\s*[Ss]eat", text)
                if seats:
                    bus_info["seats"] = seats.group(1) + " seats"

                buses.append(bus_info)
                log.debug(f"  Card parsed: {bus_info}")
            except Exception as ex:
                log.debug(f"  Card parse error: {ex}")

    # ── Strategy 2: full-page text scan ───────────────────────────────────
    # Most reliable fallback — checks if the bus name literally appears
    # anywhere on the rendered page, regardless of HTML structure.
    if not buses:
        log.info("  No structured cards found — trying full-page text scan")
        try:
            full_text = page.inner_text("body")

            for preferred in CONFIG["preferred_buses"]:
                if preferred.lower() in full_text.lower():
                    log.info(f"  Found '{preferred}' via text scan")
                    idx     = full_text.lower().find(preferred.lower())
                    context = full_text[max(0, idx - 30): idx + 250]

                    times = re.findall(r"\d{1,2}:\d{2}\s*(?:AM|PM)?", context)
                    fare  = re.search(r"(?:BDT|Tk\.?|TK|৳)\s*[\d,]+", context, re.IGNORECASE)

                    buses.append({
                        "name":      preferred,
                        "departure": times[0].strip() if times else "",
                        "arrival":   times[1].strip() if len(times) > 1 else "",
                        "fare":      fare.group(0) if fare else "",
                        "seats":     "",
                    })
        except Exception as ex:
            log.warning(f"  Full-page scan error: {ex}")

    return buses


def check_for_preferred(buses: list[dict]) -> list[dict]:
    """Return buses that match preferred names and fall within the time window."""
    matched = []
    for bus in buses:
        for preferred in CONFIG["preferred_buses"]:
            if preferred.lower() in bus.get("name", "").lower():
                if time_in_window(bus.get("departure", "")):
                    matched.append(bus)
                break
    return matched


def format_notification(matched: list[dict]) -> tuple:
    title = f"TICKET FOUND: {CONFIG['from_city']} to {CONFIG['to_city']}"
    lines = [
        f"Date: {CONFIG['date']}",
        f"Route: {CONFIG['from_city']} -> {CONFIG['to_city']}",
        "",
    ]
    for b in matched:
        line = f"* {b['name']}"
        if b.get("departure"):
            line += f"  Dep: {b['departure']}"
        if b.get("arrival"):
            line += f"  Arr: {b['arrival']}"
        if b.get("fare"):
            line += f"  {b['fare']}"
        if b.get("seats"):
            line += f"  ({b['seats']})"
        lines.append(line)
    lines += ["", "-> Open Shohoz now and book!"]
    return title, "\n".join(lines)


def run():
    log.info("=" * 55)
    log.info("  Shohoz Ticket Watcher started")
    log.info(f"  Route   : {CONFIG['from_city']} -> {CONFIG['to_city']}")
    log.info(f"  Date    : {CONFIG['date']}")
    log.info(f"  Buses   : {', '.join(CONFIG['preferred_buses'])}")
    log.info(f"  Time    : {CONFIG['time_from'] or 'any'} - {CONFIG['time_to'] or 'any'}")
    log.info(f"  Interval: {CONFIG['check_interval_seconds']}s")
    log.info(f"  ntfy    : {CONFIG['ntfy_topic']}")
    log.info("=" * 55)

    send_notification(
        "Shohoz Watcher started",
        f"Watching: {', '.join(CONFIG['preferred_buses'])}\n"
        f"Route: {CONFIG['from_city']} -> {CONFIG['to_city']}\n"
        f"Date: {CONFIG['date']}\n"
        f"Time window: {CONFIG['time_from'] or 'any'} - {CONFIG['time_to'] or 'any'}",
    )

    start_time       = time.time()
    stop_after       = CONFIG["stop_after_hours"] * 3600
    check_count      = 0
    already_notified = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="en-US",
        )
        page = context.new_page()

        try:
            while True:
                if stop_after > 0 and (time.time() - start_time) >= stop_after:
                    log.info(f"Stop time reached ({CONFIG['stop_after_hours']}h). Exiting.")
                    send_notification("Shohoz Watcher stopped", "Reached configured stop time.")
                    break

                check_count += 1
                log.info(f"Check #{check_count} at {datetime.now().strftime('%H:%M:%S')}")

                try:
                    buses = scrape_buses(page)
                    log.info(f"  Total buses found   : {len(buses)}")

                    if buses:
                        matched = check_for_preferred(buses)
                        log.info(f"  Preferred matched   : {len(matched)}")

                        new_matches = [b for b in matched if b["name"] not in already_notified]

                        if new_matches:
                            title, body = format_notification(new_matches)
                            send_notification(title, body, build_url())
                            for b in new_matches:
                                already_notified.add(b["name"])
                            log.info(f"  NOTIFIED for: {[b['name'] for b in new_matches]}")
                        else:
                            log.info("  No new matches (already notified or none preferred)")
                    else:
                        log.info("  No buses yet — tickets not released")

                except Exception as e:
                    log.error(f"  Check error: {e}")

                log.info(f"  Next check in {CONFIG['check_interval_seconds']}s\n")
                time.sleep(CONFIG["check_interval_seconds"])

        except KeyboardInterrupt:
            log.info("\nStopped by user (Ctrl+C)")
            send_notification("Shohoz Watcher stopped", "Stopped manually.")
        finally:
            browser.close()


if __name__ == "__main__":
    run()
