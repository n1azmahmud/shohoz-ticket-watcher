# 🚌 Shohoz Ticket Watcher

Automatically monitors [Shohoz.com](https://www.shohoz.com) every 5 minutes and sends an instant push notification to your Android phone the moment your preferred bus tickets become available.

> Tired of missing tickets because Shohoz releases them without warning? This script watches for you 24/7 and alerts you the second your bus shows up.

---

## How It Works

```
Every 5 minutes:
  1. A headless browser silently loads your Shohoz search URL
  2. Waits for the page to fully render (Shohoz uses React)
  3. Scans the bus listings for your preferred bus names
  4. If found → sends a push notification to your phone via ntfy.sh
  5. You tap the notification → Shohoz opens → you book the ticket
```

---

## Requirements

| Requirement | Notes |
|---|---|
| Windows / Mac / Linux PC | Must stay on while watching |
| Python 3.10 or newer | [python.org/downloads](https://python.org/downloads) |
| Android phone | For push notifications |
| Internet connection | Must be a Bangladeshi IP |

---

## Setup Guide

### Step 1 — Install Python

1. Go to **[python.org/downloads](https://python.org/downloads)**
2. Download and run the installer
3. ⚠️ On the **first screen**, tick **"Add python.exe to PATH"** before clicking anything

   ```
   ┌──────────────────────────────────────────┐
   │  Install Python 3.x.x                    │
   │                                          │
   │  ☐ Install launcher for all users        │
   │  ☑ Add python.exe to PATH   ← TICK THIS  │
   │                                          │
   │  [ Install Now ]                         │
   └──────────────────────────────────────────┘
   ```

4. Click **Install Now**

---

### Step 2 — Install Dependencies

Open **PowerShell** or **Command Prompt** and run:

```powershell
pip install playwright requests
python -m playwright install chromium
```

> `playwright install chromium` downloads a headless browser (~150 MB). This is a one-time step.

---

### Step 3 — Set Up Push Notifications (ntfy)

This project uses **[ntfy.sh](https://ntfy.sh)** — a free, no-account-needed push notification service.

1. Install the **ntfy** app on your Android phone:
   [▶ Download from Google Play Store](https://play.google.com/store/apps/details?id=io.heckel.ntfy)

2. Open the app → tap **＋** (Subscribe to topic)

3. Enter a topic name — something unique to you, like:
   ```
   shohoz-alerts-yourname-2026
   ```
   > Keep this private. Anyone who knows your topic name can receive your notifications.

4. Tap **Subscribe**

You will use this exact topic name in the script config below.

---

### Step 4 — Configure the Script

Open `script.py` in any text editor (Notepad works fine) and edit the `CONFIG` block near the top:

```python
CONFIG = {
    # Must match your ntfy app topic exactly
    "ntfy_topic": "shohoz-alerts-yourname-2026",

    # Your route
    "from_city": "Dinajpur",
    "to_city":   "Dhaka",
    "date":      "01-Jun-2026",    # Format: DD-Mon-YYYY

    # Bus names to watch for (partial match, case-insensitive)
    # Add as many as you like, or keep just one
    "preferred_buses": [
        "Nabil",
    ],

    # Optional: only notify for buses in this departure time window (24h format)
    # Leave both as "" to accept any departure time
    "time_from": "",    # e.g. "20:00"
    "time_to":   "",    # e.g. "00:00"  (00:00 means midnight / end of day)

    # Check interval in seconds (300 = every 5 minutes)
    "check_interval_seconds": 300,

    # Auto-stop after N hours. Set 0 to run forever.
    "stop_after_hours": 0,
}
```

**Common bus name values:**

| Bus | Value to use in config |
|---|---|
| Nabil Paribahan | `"Nabil"` |
| SHYAMOLI PARIBAHAN | `"Shyamoli"` |
| S.R Travels (Pvt) Ltd | `"S.R"` |
| Hanif Enterprise | `"Hanif"` |
| Green Line | `"Green Line"` |

---

### Step 5 — Run the Watcher

```powershell
python script.py
```

Within a few seconds you should receive a **"Shohoz Watcher started"** notification on your phone — this confirms everything is connected correctly.

The terminal will show a live log:

```
2026-06-01 10:00:00  INFO     =======================================================
2026-06-01 10:00:00  INFO       Shohoz Ticket Watcher started
2026-06-01 10:00:00  INFO       Route   : Dinajpur -> Dhaka
2026-06-01 10:00:00  INFO       Date    : 01-Jun-2026
2026-06-01 10:00:00  INFO       Buses   : Nabil
2026-06-01 10:00:00  INFO     =======================================================
2026-06-01 10:00:02  INFO     Notification sent OK: Shohoz Watcher started
2026-06-01 10:00:02  INFO     Check #1 at 10:00:02
2026-06-01 10:00:10  INFO       Total buses found   : 0
2026-06-01 10:00:10  INFO       No buses yet — tickets not released
2026-06-01 10:00:10  INFO       Next check in 300s
```

When your bus is released:

```
2026-06-01 14:32:01  INFO     Check #52 at 14:32:01
2026-06-01 14:32:09  INFO       Total buses found   : 3
2026-06-01 14:32:09  INFO       Preferred matched   : 1
2026-06-01 14:32:09  INFO       NOTIFIED for: ['Nabil']
```

Your phone buzzes: **"TICKET FOUND: Dinajpur to Dhaka"** — tap it to open Shohoz and book.

---

### Step 6 — Keep It Running

**Option A — Simple:** Leave the PowerShell window open. Press `Ctrl+C` to stop.

**Option B — Minimized in background:** Minimize the window. The script keeps running.

**Option C — Auto-start with Windows:**
1. Press `Win + R`, type `shell:startup`, press Enter
2. Create a shortcut to `script.py` in the folder that opens
3. The watcher will start automatically every time Windows boots

**Option D — Run on a VPS (most reliable):**
If your PC might turn off, rent a cheap Linux server (Hetzner ~€4/mo, DigitalOcean ~$5/mo) and run:
```bash
nohup python script.py > watcher.log 2>&1 &
```

---

## Troubleshooting

| Problem | Solution |
|---|---|
| `pip` not recognized | Reinstall Python and tick "Add to PATH" on the first screen |
| `playwright` not recognized | Use `python -m playwright install chromium` instead |
| No startup notification on phone | Check ntfy topic — must be identical in config and in the app |
| Always shows 0 buses | Set `"debug": True` in config, re-run, and read the page text in logs |
| Notification sent but wrong bus | Use a shorter partial name e.g. `"Nabil"` instead of the full name |
| Script crashes | Open a GitHub issue and paste the full error from the terminal |

---

## File Structure

```
shohoz-ticket-watcher/
│
├── script.py   ← main script (edit CONFIG at the top)
└── README.md           ← this file
```

---

## Notes

- The script won't send duplicate notifications — once it alerts you about a bus, it won't notify again for that same bus in the same session.
- Shohoz blocks requests from outside Bangladesh, so the script must run on a PC or server with a Bangladeshi IP address.
- If Shohoz updates their website and the script stops detecting buses, enable `"debug": True` in config and check the logged page text to see what is being loaded.

---

## License

MIT — free to use, modify, and share.
