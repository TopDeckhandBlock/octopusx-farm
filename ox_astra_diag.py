"""gpt-6-astra: read 503 body + try via local gateway :16433."""
import json, urllib.request, urllib.error

def post(url, payload, headers, timeout=90):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore")[:300]
        return e.code, body

# 1) direct upstream — capture the 503 body
lines = [l for l in open("C:/Users/User/tmp/octopusx_accounts.jsonl", encoding="utf-8") if l.strip()]
acc = json.loads(lines[-1])
key = acc["keys"][0]
hdrs = json.load(open("C:/Users/User/tmp/octopusx_keys.json", encoding="utf-8"))["upstream_headers"]
hdrs["Content-Type"] = "application/json"
hdrs["Authorization"] = f"Bearer {key}"

code, body = post("https://octopusx.ai/v1/chat/completions",
                  {"model": "gpt-6-astra", "messages": [{"role": "user", "content": "say PONG"}], "max_tokens": 20},
                  hdrs)
print(f"direct gpt-6-astra: {code} | {body[:200]}")

# 2) via local gateway (key pool + rotation + retry budget)
gw_hdrs = {"Content-Type": "application/json", "Authorization": "Bearer eni-local"}
code2, body2 = post("http://127.0.0.1:16433/v1/chat/completions",
                    {"model": "gpt-6-astra", "messages": [{"role": "user", "content": "say PONG"}], "max_tokens": 20},
                    gw_hdrs)
txt = ""
if isinstance(body2, dict):
    txt = ((body2.get("choices") or [{}])[0].get("message", {}) or {}).get("content", "")
print(f"gateway gpt-6-astra: {code2} | {txt[:60]!r} | {str(body2)[:150]}")