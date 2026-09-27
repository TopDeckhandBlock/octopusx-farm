import json, urllib.request, urllib.error, socket

socket.setdefaulttimeout(40)
BASE = "https://octopusx.ai"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/153.0.0.0 Safari/537.36",
      "Origin": "https://octopusx.ai", "Referer": "https://octopusx.ai/console/"}

lines = [l for l in open("C:/Users/User/tmp/octopusx_accounts.jsonl", encoding="utf-8") if l.strip()]
acc = json.loads(lines[-1])
auth = {**UA, "Authorization": f"Bearer {acc['jwt']}", "Content-Type": "application/json"}
print("account:", acc["email"])

req = urllib.request.Request(BASE + "/app/topup/pay",
    data=json.dumps({"provider": "stripe", "amount": 10}).encode(),
    method="POST", headers=auth)
try:
    with urllib.request.urlopen(req, timeout=40) as r:
        out = json.loads(r.read().decode())
except urllib.error.HTTPError as e:
    out = json.loads(e.read().decode())
print(json.dumps(out, indent=2)[:1500])
if out.get("code") == 0 and out.get("data", {}).get("pay_url"):
    open("C:/Users/User/tmp/ox_stripe_url.txt", "w").write(out["data"]["pay_url"])
    print("\nURL saved -> ox_stripe_url.txt")