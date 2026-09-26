"""Sweep all octopusx models through the local rotator (:16433)."""
import json
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROT = "http://127.0.0.1:16433/v1/chat/completions"
CAT = "C:/Users/User/tmp/octopusx_catalog.json"
OUT = "C:/Users/User/tmp/octopusx_sweep.json"


def probe(model):
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": "Say OK"}],
                       "max_tokens": 8}).encode()
    req = urllib.request.Request(ROT, data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            d = json.loads(r.read())
            content = ((d.get("choices") or [{}])[0].get("message") or {}).get("content", "")
            return {"model": model, "status": "OK", "content": str(content)[:60]}
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read())["error"]["message"][:110]
        except Exception:
            msg = ""
        return {"model": model, "status": f"HTTP {e.code}", "error": msg}
    except Exception as e:
        return {"model": model, "status": "ERR", "error": str(e)[:80]}


models = sorted({ln.split()[0] for ln in open(CAT, encoding="utf-8").read().replace("\\n", "\n").splitlines() if ln.strip()})
print(f"probing {len(models)} models via :16433 ...", flush=True)
with ThreadPoolExecutor(max_workers=10) as ex:
    results = list(ex.map(probe, models))

json.dump(results, open(OUT, "w", encoding="utf-8"), indent=2)
ok = [r for r in results if r["status"] == "OK"]
print(f"\nWORKING ({len(ok)}):")
for r in ok:
    print(f"  {r['model']}")
print(f"\ndead: {len(results) - len(ok)} -> {OUT}")
