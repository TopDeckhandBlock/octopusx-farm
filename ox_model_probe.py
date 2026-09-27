"""Multi-model live probe: which models actually respond."""
import json, urllib.request, urllib.error

lines = [l for l in open("C:/Users/User/tmp/octopusx_accounts.jsonl", encoding="utf-8") if l.strip()]
key = json.loads(lines[-1])["keys"][0]
hdrs = json.load(open("C:/Users/User/tmp/octopusx_keys.json", encoding="utf-8"))["upstream_headers"]
hdrs["Content-Type"] = "application/json"
hdrs["Authorization"] = f"Bearer {key}"

for model in ("gpt-6-astra", "gpt-5.6-luna", "gpt-5.6-sol", "gpt-5.6-terra", "gpt-4o-mini", "deepseek-v4-pro"):
    payload = json.dumps({"model": model, "messages": [{"role": "user", "content": "say PONG"}], "max_tokens": 20}).encode()
    req = urllib.request.Request("https://octopusx.ai/v1/chat/completions", data=payload, headers=hdrs, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            out = json.load(r)
            msg = (out.get("choices") or [{}])[0].get("message", {}).get("content", "")
            print(f"{model:22s} OK   -> {msg[:30]!r}")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore")
        reason = ""
        try:
            reason = json.loads(body).get("error", {}).get("message", "")[:60]
        except Exception:
            reason = body[:60]
        print(f"{model:22s} {e.code}  <- {reason}")
    except Exception as e:
        print(f"{model:22s} ERR  <- {str(e)[:60]}")