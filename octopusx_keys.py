import json, urllib.request, urllib.error

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36"

def call(url, key, data=None):
    h = {
        "User-Agent": UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US",
        "Origin": "https://octopusx.ai",
        "Referer": "https://octopusx.ai/console/",
        "Authorization": f"Bearer {key}",
    }
    if data:
        h["Content-Type"] = "application/json;charset=UTF-8"
        body = json.dumps(data).encode()
    else:
        body = None
    req = urllib.request.Request(url, data=body, headers=h, method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return r.status, r.read().decode(errors="replace")[:400]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")[:400]

KEYS = {
    "user_key": "sk-CK0qxUL4ldJWlLAQPcPfJzVSs8iQ7E4g7288bxTj2M7zGpLk",
    "fresh_key": "sk-egDLREROhdTYHCmwSssUFKzEdwjHfi2kEdpSyS2jCsTowNK3",
}

for name, key in KEYS.items():
    s, b = call("https://octopusx.ai/v1/models", key)
    print(f"== {name} /v1/models [{s}] {b[:200]}")
    for model in ["gpt-6-astra", "deepseek-v4-flash", "kimi-k3", "glm-5.3", "gemini-3.1-flash"]:
        s, b = call("https://octopusx.ai/v1/chat/completions", key,
                    {"model": model, "messages": [{"role": "user", "content": "Say OK"}], "max_tokens": 8})
        print(f"   {model:20s} [{s}] {b[:150]}")
    print()
