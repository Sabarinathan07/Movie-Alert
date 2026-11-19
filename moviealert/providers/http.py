"""HTTP fetching with optional India egress (ScraperAPI / proxy).

Both sites block non-India and datacenter IPs for some pages. From an India
VPS or home connection a plain request works; from GitHub runners BMS needs
SCRAPERAPI_KEY or PROXY_URL.
"""

import os
import urllib.parse

import requests

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9",
}


def fetch(url, warmup=None, direct_ok=None):
    """GET a page.

    direct_ok: optional predicate(text) -> bool. When given and a ScraperAPI
    key is configured, a plain request is tried first and a ScraperAPI credit
    is spent only if the predicate fails (i.e. we were blocked).
    """
    key = os.environ.get("SCRAPERAPI_KEY")
    if key and direct_ok:
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.ok and direct_ok(r.text):
                return r.text
            print(f"[fetch] direct got {r.status_code}, falling back to ScraperAPI")
        except requests.RequestException as e:
            print(f"[fetch] direct failed ({e}), falling back to ScraperAPI")
    if key:
        api = "https://api.scraperapi.com/?" + urllib.parse.urlencode(
            {"api_key": key, "country_code": "in", "url": url}
        )
        r = requests.get(api, timeout=90)
        r.raise_for_status()
        return r.text

    proxy = os.environ.get("PROXY_URL")
    proxies = {"http": proxy, "https": proxy} if proxy else None
    s = requests.Session()
    s.headers.update(HEADERS)
    if warmup:
        try:
            s.get(warmup, timeout=30, proxies=proxies)
        except requests.RequestException:
            pass
    r = s.get(url, timeout=30, proxies=proxies)
    r.raise_for_status()
    return r.text
