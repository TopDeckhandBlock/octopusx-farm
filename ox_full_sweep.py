"""Full availability sweep: all 98 catalog models, parallel probe with the fresh key."""
import json, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor

lines = [l for l in open("C:/Users/User/tmp/octopusx_accounts.jsonl", encoding="utf-8") if l.strip()]
key = json.loads(lines[-1])["keys"][0]
hdrs = json.load(open("C:/Users/User/tmp/octopusx_keys.json", encoding="utf-8"))["upstream_headers"]
hdrs["Content-Type"] = "application/json"
hdrs["Authorization"] = f"Bearer {key}"

req0 = urllib.request.Request("https://octopusx.ai/v1/models", headers=hdrs)
with urllib.request.urlopen(req0, timeout=30) as r:
    ids = sorted({m["id"] for m in json.load(r).get("data", [])})
print(f"probing {len(ids)} models...")


def probe(model):
    payload = json.dumps({"model": model, "messages": [{"role": "user", "content": "say PONG"}], "max_tokens": 8}).encode()
    req = urllib.request.Request("https://octopusx.ai/v1/chat/completions", data=payload, headers=hdrs, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            out = json.load(r)
            msg = (out.get("choices") or [{}])[0].get("message", {}).get("content", "")
            return model, "OK", msg.strip()[:25]
    except urllib.error.HTTPError as e:
        try:
            reason = json.loads(e.read().decode("utf-8", "ignore")).get("error", {}).get("message", "")[:40]
        except Exception:
            reason = ""
        return model, str(e.code), reason
    except Exception as e:
        return model, "ERR", str(e)[:40]


ok, dead = [], []
with ThreadPoolExecutor(max_workers=16) as ex:
    for model, status, note in ex.map(probe, ids):
        (ok if status == "OK" else dead).append((model, status, note))

print(f"\n=== ALIVE ({len(ok)}) ===")
for m, s, n in sorted(ok):
    print(f"  {m:28s} -> {n!r}")
print(f"\n=== DEAD ({len(dead)}) ===")
for m, s, n in sorted(dead):
    print(f"  {m:28s} {s:5s} {n}")