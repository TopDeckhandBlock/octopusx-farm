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
]
OUT_PATH = "octopusx_proxies.json"
TEST_URL = "https://api.ipify.org/?format=json"
TIMEOUT = 8
THREADS = 60
MAX_PROXIES = 300


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
    return list(found)[:MAX_PROXIES * 3]


def test_proxy(pp):
    """True if proxy answers HTTPS CONNECT with a valid response (real proxy)."""
    try:
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": f"http://{pp}", "https": f"http://{pp}"}))
        req = urllib.request.Request(TEST_URL, headers={"User-Agent": "Mozilla/5.0"})
        with opener.open(req, timeout=TIMEOUT) as r:
            body = r.read().decode("utf-8", "ignore")
            return "ip" in body and r.status == 200
    except Exception:
        return False


def refresh():
    """Fetch + validate; returns list of http://ip:port strings (may be empty)."""
    raw = fetch_lists()
    print(f"[proxies] fetched {len(raw)} candidates from {len(SOURCES)} lists")
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


def pick():
    """Random alive proxy or None. Usage: _tls.proxy = pick() per account."""
    lst = load()
    return random.choice(lst) if lst else None


if __name__ == "__main__":
    a = refresh()
    print(f"saved {len(a)} to {OUT_PATH}")
    for x in a[:10]:
        print(" ", x)
