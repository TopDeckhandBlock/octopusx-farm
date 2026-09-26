#!/usr/bin/env python3
"""Per-key alive check: every key does a real GET /v1/models against OctopusX."""
import concurrent.futures
import json
import ssl
import time
import urllib.error
import urllib.request

CFG = json.load(open("octopusx_keys.json", encoding="utf-8-sig"))
KEYS = CFG["keys"]
BASE = (CFG.get("base_url") or "").rstrip("/")
H = CFG.get("upstream_headers") or {}
CTX = ssl.create_default_context()


def check(ik):
    i, k = ik
    req = urllib.request.Request(BASE + ("/models" if BASE.endswith("/v1") else "/v1/models"))
    req.add_header("Authorization", "Bearer " + k)
    for h, v in H.items():
        req.add_header(h, v)
    try:
        with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
            return {"i": i, "status": r.status, "err": ""}
    except urllib.error.HTTPError as e:
        return {"i": i, "status": e.code, "err": e.read()[:150].decode("utf-8", "ignore")}
    except Exception as e:
        return {"i": i, "status": 0, "err": f"{type(e).__name__}: {str(e)[:100]}"}


t0 = time.time()
with concurrent.futures.ThreadPoolExecutor(12) as ex:
    res = list(ex.map(check, enumerate(KEYS)))

alive = [r for r in res if r["status"] == 200]
dead = [r for r in res if r["status"] != 200]
by = {}
for r in res:
    by[r["status"]] = by.get(r["status"], 0) + 1

out = {
    "checked": len(res), "alive": len(alive), "dead": len(dead),
    "by_status": {str(k): v for k, v in by.items()},
    "elapsed_s": round(time.time() - t0, 1),
    "dead_detail": dead[:50],
}
json.dump(out, open("octopusx_alive.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps({k: out[k] for k in ("checked", "alive", "dead", "by_status", "elapsed_s")}, indent=1))
if dead:
    print("sample dead:", json.dumps(dead[:5], indent=1))
