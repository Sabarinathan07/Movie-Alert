"""Alert channels. Account-level credentials come from the environment;
per-person destinations (chat id, phone, Telegram handle) come from the User.

    TELEGRAM_BOT_TOKEN                           -> messages (free)
    TWILIO_ACCOUNT_SID / _AUTH_TOKEN / _FROM     -> phone calls (paid, primary)
    CallMeBot (no key, user authorises once)     -> Telegram calls (free, best effort)
"""

import os
import re

import requests

from .config import User


def telegram_message(user: User, text: str) -> bool:
    tok = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not (tok and user.telegram_chat_id):
        print(f"[telegram:{user.id}] not configured")
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{tok}/sendMessage",
            json={"chat_id": user.telegram_chat_id, "text": text,
                  "disable_web_page_preview": True},
            timeout=30,
        )
        print(f"[telegram:{user.id}] {r.status_code}")
        return r.ok
    except requests.RequestException as e:
        print(f"[telegram:{user.id}] failed: {e}")
        return False


def twilio_call(user: User, spoken: str) -> bool:
    sid, auth = os.environ.get("TWILIO_ACCOUNT_SID"), os.environ.get("TWILIO_AUTH_TOKEN")
    frm = os.environ.get("TWILIO_FROM")
    if not (sid and auth and frm and user.phone):
        print(f"[twilio:{user.id}] not configured")
        return False
    say = re.sub(r"[<>&]", " ", spoken)
    twiml = (f'<Response><Say voice="alice" language="en-IN">{say}</Say><Pause length="1"/>'
             f'<Say voice="alice" language="en-IN">{say}</Say></Response>')
    try:
        r = requests.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Calls.json",
            data={"To": user.phone, "From": frm, "Twiml": twiml},
            auth=(sid, auth), timeout=30,
        )
        print(f"[twilio:{user.id}] {r.status_code} {'call queued' if r.ok else r.text[:200]}")
        return r.ok
    except requests.RequestException as e:
        print(f"[twilio:{user.id}] failed: {e}")
        return False


def callmebot_call(user: User, spoken: str) -> bool:
    if not user.callmebot_user:
        return False
    try:
        r = requests.get(
            "https://api.callmebot.com/start.php",
            params={"user": user.callmebot_user, "text": spoken[:250],
                    "lang": "en-IN-Standard-A", "rpt": 3},
            timeout=120,
        )
        # CallMeBot answers HTTP 200 even when it skips the call ("FLOOD").
        err = re.search(r"Error:[^\n]{0,120}", re.sub(r"<[^>]+>", " ", r.text))
        print(f"[callmebot:{user.id}] {r.status_code} {err.group(0) if err else 'call started'}")
        return r.ok and not err
    except requests.RequestException as e:
        print(f"[callmebot:{user.id}] failed: {e}")
        return False


def call(user: User, spoken: str) -> bool:
    """Twilio phone call first (reliable), Telegram call as an extra."""
    if not user.calls:
        return False
    ok_twilio = twilio_call(user, spoken)
    ok_tg = callmebot_call(user, spoken)
    return ok_twilio or ok_tg
