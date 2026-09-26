import json, urllib.request, urllib.error, time

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36"
BASE = "https://octopusx.ai"
JWT = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1aWQiOjExODcsImp0aSI6ImQzZWEwMjIwLTNkNjUtNDE0NS1hMGU3LWI1Njg1ODk4ZDljOCIsInJldiI6MCwiaWF0IjoxNzkwNDYxNTIxLCJleHAiOjE3OTEwNjYzMjF9.E-tGe4jfIHaQx8A1dlfbXwLTFfqlZTtEyOSUXuFwGtk"

def http(path, data=None, method=None):
    h = {
        "User-Agent": UA, "Accept": "application/json, text/plain, */*", "Accept-Language": "en-US",
        "Origin": BASE, "Referer": BASE + "/console/",
    }
    if data is not None:
        h["Content-Type"] = "application/json;charset=UTF-8"
    if method == "POST" or data is not None:
        h["Authorization"] = f"Bearer {JWT}"
    req = urllib.request.Request(BASE + path, data=json.dumps(data).encode() if data is not None else None,
                                 headers=h, method=method or ("POST" if data is not None else "GET"))
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read())

def chat(key, model):
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": "Say OK"}], "max_tokens": 8}).encode()
    req = urllib.request.Request(BASE + "/v1/chat/completions", data=body, headers={
        "User-Agent": UA, "Accept": "application/json, text/plain, */*", "Accept-Language": "en-US",
        "Origin": BASE, "Referer": BASE + "/console/",
        "Authorization": f"Bearer {key}", "Content-Type": "application/json;charset=UTF-8",
    }, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            d = json.loads(r.read())
            return "OK " + repr((d.get("choices") or [{}])[0].get("message", {}).get("content", ""))[:80]
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code} " + e.read().decode(errors="replace")[:120]

# variants of token creation payload
variants = [
    ("per_call", {"project_id": 1268, "name": "percall", "allow_pay_mode": 1, "spend_quota": 0, "unlimited_quota": True, "quota_refresh": "never"}),
    ("per_call_quota", {"project_id": 1268, "name": "pq", "allow_pay_mode": 1, "spend_quota": 100000, "unlimited_quota": False, "quota_refresh": "monthly"}),
]
for name, payload in variants:
    try:
        r = http("/app/token/", payload)
        key = r.get("data", {}).get("key")
        print(f"== {name}: created {key[:16]}... full={key}")
        for m in ["gpt-6-astra", "deepseek-v4-flash", "gpt-4o-mini"]:
            print(f"   {m:20s} {chat(key, m)}")
    except urllib.error.HTTPError as e:
        print(f"== {name}: create failed HTTP {e.code}: {e.read().decode(errors='replace')[:200]}")
    time.sleep(1)

# also: wallet quota now?
self = http("/app/user/self", method="GET")
print("wallet:", json.dumps(self["data"]["wallet"]))
tasks = http("/app/user/guide/tasks", method="GET")
print("tasks:", json.dumps(tasks["data"]["tasks"], ensure_ascii=False)[:600])
