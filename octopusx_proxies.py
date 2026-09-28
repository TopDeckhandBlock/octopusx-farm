"""Free proxy pool for OctopusX farm: fetch public lists, validate, save alive.

Usage: python octopusx_proxies.py            (fetch + validate + save)
       import octopusx_proxies; octopusx_proxies.refresh()
(public "alive" lists are ~95% dead / CDN endpoints, so we test ourselves).
"""
import json
import os
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
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
    # proxy-workbench catalog (github.com/DavidVoitenko/proxy-workbench)
    "https://raw.githubusercontent.com/MuRongPIG/Proxy-Master/main/http.txt",
    "https://proxyspace.pro/http.txt",
    "https://api.proxyscrape.com/v4/free-proxy-list/get?request=display_proxies&protocol=http&proxy_format=ipport&format=text",
    "https://raw.githubusercontent.com/rdavydov/proxy-list/main/proxies/http.txt",
    "https://raw.githubusercontent.com/Zaeem20/FREE_PROXIES_LIST/master/https.txt",
    "https://raw.githubusercontent.com/zloi-user/hideip.me/main/https.txt",
    "https://cdn.jsdelivr.net/gh/proxyscrape/free-proxy-list@main/proxies/protocols/https/data.txt",
    "https://raw.githubusercontent.com/relayglass/free-proxy-list/main/protocol/https/https.txt",
    "https://raw.githubusercontent.com/dinoz0rg/proxy-list/main/checked_proxies/http.txt",
    "https://raw.githubusercontent.com/databay-labs/free-proxy-list/master/http.txt",
    "https://raw.githubusercontent.com/Vann-Dev/proxy-list/main/proxies/http.txt",
    "https://cdn.jsdelivr.net/gh/proxyscrape/free-proxy-list@main/proxies/protocols/http/data.txt",
    "https://raw.githubusercontent.com/Anonym0usWork1221/Free-Proxies/main/proxy_files/http_proxies.txt",
    "https://raw.githubusercontent.com/ObcbO/getproxy/master/file/http.txt",
    "https://raw.githubusercontent.com/casals-ar/proxy-list/main/http",
    "https://raw.githubusercontent.com/hproxy-com/free-proxy-list/main/https.txt",
    "https://raw.githubusercontent.com/hproxy-com/free-proxy-list/main/http.txt",
    "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt",
    "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-http.txt",
    "https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/http.txt",
    "https://raw.githubusercontent.com/zloi-user/hideip.me/main/http.txt",
    "https://raw.githubusercontent.com/zloi-user/hideip.me/main/https.txt",
    "https://raw.githubusercontent.com/mmpx12/proxy-list/master/https.txt",
]
OUT_PATH = "octopusx_proxies.json"
TEST_URL = "https://api.mail.tm/domains"  # the endpoint that actually matters
TIMEOUT = 12
THREADS = 120
MAX_PROXIES = 3000

_dead = set()  # in-flight failures; process-local memory of dead proxies
_mail_cd = {}  # proxy -> cooldown-until ts; mail.tm 429 per-IP quota
# --- BrightData zones (paid, always-alive). Creds pulled from panel ->
# brd_creds.json via brd_get_creds.py (connect.sid cookies; API token 401).
# - datacenter_proxy1: rotating dc; sessid suffix = sticky per-session IP,
#   each sessid gets its own mail.tm per-IP quota (fixes the 429 ceiling).
# - isp_proxy1/isp_proxy2 (res_static): zone user routes via assigned static IP.
BRD_CID = "brd-customer-hl_2e228c6c"
BRD_HOST = "brd.superproxy.io:44445"
BRD_DC_SESS = 300  # sticky dc sessions = independent per-IP quotas


def brd_proxies():
    """All BrightData zones from brd_creds.json (+ dc sessid fanout)."""
    try:
        creds = json.load(open(os.path.join(os.path.dirname(__file__),
                                            "brd_creds.json")))
    except Exception as e:
        print(f"[proxies] brd_creds.json missing: {e}", flush=True)
        creds = {}
    out = []
    for name, z in creds.items():
        pw = z.get("password")
        if not pw or z.get("product") in ("unblocker", "browser_api"):
            continue
        if z.get("product") == "dc":
            for i in range(BRD_DC_SESS):
                out.append(f"http://{BRD_CID}-zone-{name}-session-f{i:03d}:{pw}@{BRD_HOST}")
        else:
            # res_static: enumerate assigned IPs if known, else bare zone user
            ips = z.get("ips")
            if isinstance(ips, list) and ips:
                out += [f"http://{BRD_CID}-zone-{name}-ip-{ip}:{pw}@{BRD_HOST}" for ip in ips]
            else:
                out.append(f"http://{BRD_CID}-zone-{name}:{pw}@{BRD_HOST}")
    return out


def _merge_brd(alive):
    """Always-alive paid IPs: append untested (super-proxy uptime ~100%)."""
    brd = brd_proxies()
    added = [p for p in brd if p not in alive]
    if added:
        print(f"[proxies] +{len(added)} BrightData zone URLs", flush=True)
    return alive + added


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


POOL_TTL = 1200  # reuse saved alive-pool if younger than this (s)


def refresh(force: bool = False):
    """Fetch + validate; returns list of http://ip:port strings (may be empty).

    If OUT_PATH was written < POOL_TTL ago, reuse it — parallel batches skip the
    ~13-min re-check of the same 12k candidates (they were burning each other).
    """
    import os
    if not force:
        try:
            if os.path.exists(OUT_PATH) and time.time() - os.path.getmtime(OUT_PATH) < POOL_TTL:
                alive = load()
                if alive:
                    print(f"[proxies] reusing fresh pool: {len(alive)} alive "
                          f"({time.time() - os.path.getmtime(OUT_PATH):.0f}s old)", flush=True)
                    return alive
        except OSError:
            pass
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
    alive = _merge_brd(alive)
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
