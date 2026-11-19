# Movie-Alert

Get a **phone call** (plus a Telegram message) the moment tickets open — or sold-out
seats come back — for a movie at the theatres you care about, on **District** and
**BookMyShow**. Runs on **GitHub Actions**; nothing to keep running on your machine.

Currently configured for **Avengers: Doomsday · 17 Dec 2026 · Chennai · English 3D · 2 seats**:

| Priority | Theatres | Calls when |
|---|---|---|
| 1 | GK Cinemas 4K 3D, Porur | opens · seats come back |
| 2 | Any PVR / INOX **Infinity Vision 3D** | opens · sold-out early show releases ≥ 2 seats |
| 3 | AGS Maduravoyal | opens · seats come back |
| Backup | SB Cinemas, Vels | opens |

## How it works

```
GitHub Actions (cron */20, each run loops 25 min) ──every 60 s──▶ watcher.py
                                                       │
     District public showtimes page (__NEXT_DATA__) ◀──┤  per show: format, language,
     BookMyShow buytickets page (venue links)       ◀──┘  seats available / total
                                                       │
                       new event? ──▶ Telegram message
                                      + Twilio phone call (primary)
                                      + CallMeBot Telegram call (best-effort extra)
```

- **OPEN** – a watched theatre starts listing the target date (District: only shows
  matching `language` + `format_must_include`; BMS: a venue link for that exact date).
- **SEATS** – a watched District show (starting before `seat_alert_shows_before`) goes
  from fewer than `seats_needed` seats to enough, or releases a batch of seats.
- The **first run** only records what's already listed and sends a Telegram summary;
  calls start from the next run. State lives in `watch_state.json` (committed by the
  workflow). Calls are rate-limited by `call_cooldown_minutes` (except new openings).
- Only public pages are read — no login, no private APIs.

## Setup

### 1. Telegram bot (messages)
Message **@BotFather** → `/newbot` → copy the token. Send the bot any message, open
`https://api.telegram.org/bot<TOKEN>/getUpdates`, copy `chat.id`.

### 2. Phone call — pick one or both
| Provider | Secrets | Cost |
|---|---|---|
| **CallMeBot** – Telegram voice call (extra) | `CALLMEBOT_TG_USER` = `@yourhandle` | Free but unreliable (often skips with "FLOOD"). Authorize by sending /start to @CallMeBot_txtbot; set Telegram Privacy → Calls → Everybody. |
| **Twilio** – real phone call (primary) | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM`, `CALL_TO` (`+91…`) | Trial calls only verified numbers and plays a trial notice first; paid ≈ $0.05–0.07/min to India. |

### 3. ScraperAPI (BookMyShow from GitHub)
BMS blocks non-India / datacenter IPs. Add `SCRAPERAPI_KEY` (scraperapi.com) or a
`PROXY_URL` India proxy. District is fetched directly first and only falls back to
ScraperAPI if blocked, to save credits.

### 4. Repo secrets
**Settings → Secrets and variables → Actions**: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`,
`SCRAPERAPI_KEY`, plus the call secrets from step 2.

### 5. Trigger it every few minutes (cron-job.org)
GitHub's own `schedule` is unreliable, so trigger externally. Create a fine-grained
PAT scoped to this repo with **Actions: Read and write**, then a cron-job.org job:

| Field | Value |
|---|---|
| URL | `https://api.github.com/repos/<you>/Movie-Alert/actions/workflows/booking-watch.yml/dispatches` |
| Method / Schedule | `POST`, every 5–10 min |
| Headers | `Accept: application/vnd.github+json`, `Authorization: Bearer <PAT>`, `X-GitHub-Api-Version: 2022-11-28` |
| Body | `{"ref":"main"}` |

## Configure — `watches.json` (v2: many users, many watches)

Design and roadmap: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

```jsonc
{
  "users": {
    "sabari": { "telegram_chat_id": "env:TELEGRAM_CHAT_ID", "phone": "env:CALL_TO",
                "callmebot_user": "env:CALLMEBOT_TG_USER", "calls": true }
  },
  "watches": [{
    "id": "doomsday-chennai",
    "users": ["sabari"],
    "movie": "Avengers: Doomsday", "date": "2026-12-17",
    "sources": {
      "district": { "url": "https://www.district.in/movies/<slug>-in-chennai-MV<id>?fromdate={date}" },
      "bms":      { "url": "https://in.bookmyshow.com/movies/chennai/<slug>/buytickets/ET<id>/{yyyymmdd}", "every_minutes": 20 }
    },
    "language": "English", "formats": ["3D"], "min_seats": 1,
    "show_from": null, "show_to": null, "call_cooldown_minutes": 10,
    "theatres": [
      { "name": "GK Porur", "match": "\\bgk\\b.*porur" },
      { "name": "Any Infinity Vision 3D", "match": ".", "format_match": "infinity vision", "sources": ["district"] }
    ]
  }]
}
```

- `"env:NAME"` values are read from the environment, so the file holds no secrets or phone numbers.
- Watches that share a page are fetched **once** per round and fanned out to every watch.
- `theatres[].match` is a case-insensitive regex on the District cinema name / BMS venue slug;
  `format_match` filters screen format (District only). Groups are checked in order.
- `watches.example.json` shows a second user with different preferences.

Find exact cinema names/IDs/formats for a watch, and validate the file:

```bash
python -m moviealert theatres doomsday-chennai
python -m moviealert check-config
```

## Run locally

```bash
pip install -r requirements.txt
python -m moviealert run --dry-run                  # what matches right now (no alerts)
python -m moviealert test-call sabari               # test Telegram + call for a user
caffeinate -i python -m moviealert run --loop 60    # every minute from your Mac (India IP)
python -m unittest discover -s tests                # engine + config tests
```

`python watcher.py [--dry-run | --loop N | --test-call]` still works (thin wrapper).

## Files

| Path | Purpose |
|---|---|
| `moviealert/` | Package: `config`, `providers/` (district, bms), `engine` (pure diff), `notify`, `runner`, CLI |
| `watches.json` / `watches.example.json` | Users + watches (no secrets; `env:` refs) |
| `watch_state.json` | Auto-managed v2 state (per watch + per page fetch times); v1 state auto-migrates |
| `tests/` | Unit tests |
| `docs/ARCHITECTURE.md` | Architecture, data model, roadmap |
| `watcher.py` | Backwards-compatible entry point |
| `poller.py`, `config.json`, `state.json` | Original single-theatre BMS poller (disabled in the workflow) |
| `.github/workflows/booking-watch.yml` | GitHub Actions runner (loops every 60 s) |
