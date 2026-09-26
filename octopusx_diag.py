import json, urllib.request, sys

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36"
JWT = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1aWQiOjExODcsImp0aSI6ImQzZWEwMjIwLTNkNjUtNDE0NS1hMGU3LWI1Njg1ODk4ZDljOCIsInJldiI6MCwiaWF0IjoxNzkwNDYxNTIxLCJleHAiOjE3OTEwNjYzMjF9.E-tGe4jfIHaQx8A1dlfbXwLTFfqlZTtEyOSUXuFwGtk"
BASE = "https://octopusx.ai"

def get(path):
    req = urllib.request.Request(BASE + path, headers={
        "User-Agent": UA, "Accept": "application/json, text/plain, */*", "Accept-Language": "en-US",
        "Origin": BASE, "Referer": BASE + "/console/",
        "Authorization": f"Bearer {JWT}",
    })
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read())

for p in ["/app/user/self", "/app/user/guide/tasks", "/app/public/registration-gift"]:
    try:
        d = get(p)
        print(f"== {p} ==")
        print(json.dumps(d, indent=1, ensure_ascii=False)[:2200])
    except Exception as e:
        print(f"== {p} == ERROR {type(e).__name__}: {e}")
