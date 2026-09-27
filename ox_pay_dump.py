import json, urllib.request, urllib.error, socket

socket.setdefaulttimeout(30)
BASE = "https://octopusx.ai"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/153.0.0.0 Safari/537.36",
      "Origin": "https://octopusx.ai", "Referer": "https://octopusx.ai/console/"}

lines = [l for l in open("C:/Users/User/tmp/octopusx_accounts.jsonl", encoding="utf-8") if l.strip()]
acc = json.loads(lines[-1])
tok = acc["jwt"]
auth = {**UA, "Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
print("account:", acc["email"], "| user_id:", acc.get("user_id"))

def call(path, payload=None, method=None):
    m = method or ("POST" if payload is not None else "GET")
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=m, headers=auth)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8", "ignore")
            return f"HTTP {r.status}: {body[:500]}"
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code}: {e.read().decode('utf-8', 'ignore')[:300]}"
    except Exception as e:
        return f"ERR: {str(e)[:80]}"

for path in ("/app/user/self", "/app/topup/overview", "/app/topup",
             "/app/billing/auto_reload", "/app/billing/budget",
             "/app/public/registration-gift", "/app/subscription/plans",
             "/app/topup/records"):
    print("\n###", path)
    print(call(path))