import json, urllib.request

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36"
BASE = "https://octopusx.ai"

def get(path):
    req = urllib.request.Request(BASE + path, headers={
        "User-Agent": UA, "Accept": "application/json, text/plain, */*", "Accept-Language": "en-US",
        "Origin": BASE, "Referer": BASE + "/",
    })
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read())

d = get("/app/public/pricing/models?type=popular")
data = d.get("data")
if isinstance(data, dict):
    items = data.get("items") or data.get("models") or data.get("list") or []
else:
    items = data or []
print("popular count:", len(items))
print(json.dumps(items[:3], indent=1, ensure_ascii=False)[:1500])
