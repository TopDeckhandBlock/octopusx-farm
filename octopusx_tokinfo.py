import json, urllib.request, urllib.error

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36"
BASE = "https://octopusx.ai"
JWT = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1aWQiOjExODcsImp0aSI6ImQzZWEwMjIwLTNkNjUtNDE0NS1hMGU3LWI1Njg1ODk4ZDljOCIsInJldiI6MCwiaWF0IjoxNzkwNDYxNTIxLCJleHAiOjE3OTEwNjYzMjF9.E-tGe4jfIHaQx8A1dlfbXwLTFfqlZTtEyOSUXuFwGtk"
H = {
    "User-Agent": UA, "Accept": "application/json, text/plain, */*", "Accept-Language": "en-US",
    "Origin": BASE, "Referer": BASE + "/console/",
    "Authorization": f"Bearer {JWT}",
}

def get(path):
    req = urllib.request.Request(BASE + path, headers=H)
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read())

tokens = get("/app/token/?team_id=1218&project_id=1268")
print(json.dumps(tokens, indent=1, ensure_ascii=False)[:3000])
