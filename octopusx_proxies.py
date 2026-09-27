"""Free proxy pool for OctopusX farm: fetch public lists, validate, save alive.

Usage: python octopusx_proxies.py            (fetch + validate + save)
       import octopusx_proxies; octopusx_proxies.refresh()
(public "alive" lists are ~95% dead / CDN endpoints, so we test ourselves).
"""
import json
import random
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

SOURCES = [
    "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=5000&country=all&ssl=all&anonymity=all",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
    "https://raw.githubusercontent.com/roosterkid/openproxylist/main/HTTPS_RAW.txt",
    "https://raw.githubusercontent.com/mmpx12/proxy-list/master/http.txt",
    "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/all/data.txt",
    "https://api.openproxylist.xyz/http.txt",
    "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt",
    "https://raw.githubusercontent.com/sunny9577/proxy-scraper/master/generated/http_proxies.txt",
    "https://raw.githubusercontent.com/zevtyardt/proxy-list/main/all.txt",
    "https://proxylist.geonode.com/api/proxy-list?limit=500&page=1&sort_by=lastChecked&sort_type=desc&protocols=http",
    # jsdelivr mirrors (raw.githubusercontent 404-resilience)
    "https://cdn.jsdelivr.net/gh/monosans/proxy-list@main/proxies/http.txt",
    "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/all/data.txt",
    "https://cdn.jsdelivr.net/gh/TheSpeedX/PROXY-List@master/http.txt",
    "https://cdn.jsdelivr.net/gh/zevtyardt/proxy-list@main/all.txt",
    "https://cdn.jsdelivr.net/gh/ProxyScrape/free-proxy-list@main/proxies/protocols/http/data.txt",
    # fresh sources
    "https://raw.githubusercontent.com/wiki/gfpcom/free-proxy-list/lists/http.txt",
    "https://vakhov.github.io/fresh-proxy-list/http.txt",
    "https://raw.githubusercontent.com/iplocate/free-proxy-list/main/protocols/http.txt",
    # wave 2
    "https://raw.githubusercontent.com/proxy4parsing/proxy-list/main/http.txt",
    "https://raw.githubusercontent.com/B4RC0DE-TM/proxy-list/main/HTTP.txt",
    "https://api.proxyscrape.com/v4/free-proxy-list/get?request=display_proxies&protocol=http",
    "https://cdn.jsdelivr.net/gh/sunny9577/proxy-scraper@master/generated/http_proxies.txt",
    "https://cdn.jsdelivr.net/gh/mmpx12/proxy-list@master/http.txt",
    "https://raw.githubusercontent.com/zloi-user/hideip.me/main/http.txt",
]
OUT_PATH = "octopusx_proxies.json"
TEST_URL = "https://api.mail.tm/domains"  # the endpoint that actually matters
TIMEOUT = 12
THREADS = 120
MAX_PROXIES = 3000

_dead = set()  # in-flight failures; process-local memory of dead proxies
_mail_cd = {}  # proxy -> cooldown-until ts; mail.tm 429 per-IP quota


def fetch_lists():
    found = set()
    for src in SOURCES:
        try:
            req = urllib.request.Request(src, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=20) as r:
                text = r.read().decode("utf-8", "ignore")
            for line in text.splitlines():
                line = line.strip()
                if line and ":" in line and line.replace(":", "").replace(".", "").isdigit():
                    found.add(line)
        except Exception as e:
            print(f"[proxies] source failed: {src.split('/')[2]}: {e}")
    return list(found)[:MAX_PROXIES * 4]


def test_proxy(pp):
    """True if proxy delivers mail.tm /domains (Cloudflare bans many ASNs)."""
    try:
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": f"http://{pp}", "https": f"http://{pp}"}))
        req = urllib.request.Request(TEST_URL, headers={"User-Agent": "Mozilla/5.0"})
        with opener.open(req, timeout=TIMEOUT) as r:
            return r.status == 200 and b"domain" in r.read()
    except Exception:
        return False


def refresh():
    """Fetch + validate; returns list of http://ip:port strings (may be empty)."""
    raw = fetch_lists()
    raw = list(set(raw) | {p.replace("http://", "") for p in load()})
    print(f"[proxies] fetched {len(raw)} candidates from {len(SOURCES)} lists (incl. pool)")
    t0 = time.time()
    alive = []
    with ThreadPoolExecutor(max_workers=THREADS) as pool:
        for pp, ok in zip(raw, pool.map(test_proxy, raw)):
            if ok:
                alive.append(f"http://{pp}")
    print(f"[proxies] alive: {len(alive)}/{len(raw)} in {time.time() - t0:.0f}s")
    json.dump(alive, open(OUT_PATH, "w"), indent=1)
    return alive


def load():
    try:
        return json.load(open(OUT_PATH))
    except Exception:
        return []


def mark_dead(p):
    """Remember a proxy that failed mid-request; pick() skips it."""
    if p:
        _dead.add(p)


def mark_mail_cd(p, seconds=1800):
    """mail.tm 429 on this IP: per-IP quota burned, cool it down 30 min."""
    if p:
        _mail_cd[p] = time.time() + seconds


def mail_cd_left(p):
    """Seconds left on mail cooldown for p (0 = fresh)."""
    return max(0, _mail_cd.get(p, 0) - time.time())


def pick():
    """Random alive (not known-dead, not mail-cooling) proxy or None."""
    now = time.time()
    lst = [p for p in load() if p not in _dead]
    fresh = [p for p in lst if _mail_cd.get(p, 0) <= now]
    return random.choice(fresh) if fresh else (random.choice(lst) if lst else None)


if __name__ == "__main__":
    a = refresh()
    print(f"saved {len(a)} to {OUT_PATH}")
    for x in a[:10]:
        print(" ", x)
