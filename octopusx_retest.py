import json, urllib.request, urllib.error, concurrent.futures

KEY = "sk-egDLREROhdTYHCmwSssUFKzEdwjHfi2kEdpSyS2jCsTowNK3"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36"
HDR = {
    "Authorization": f"Bearer {KEY}",
    "Content-Type": "application/json;charset=UTF-8",
    "User-Agent": UA, "Accept": "application/json, text/plain, */*", "Accept-Language": "en-US",
    "Origin": "https://octopusx.ai", "Referer": "https://octopusx.ai/console/",
}

MODELS = ["gpt-4o-mini", "gpt-4o", "gpt-6-astra", "gpt-5.6-sol", "claude-fable-5", "claude-sonnet-4-5",
          "deepseek-v4-flash", "gemini-2.5-flash", "kimi-k3", "grok-4", "glm-5.3", "MiniMax-M3"]

def probe(model):
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": "Say OK"}], "max_tokens": 8}).encode()
    req = urllib.request.Request("https://octopusx.ai/v1/chat/completions", data=body, headers=HDR, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.loads(r.read())
            content = (d.get("choices") or [{}])[0].get("message", {}).get("content", "")
            return (model, "OK", f"{content!r}"[:60])
    except urllib.error.HTTPError as e:
        return (model, f"HTTP {e.code}", e.read().decode(errors="replace")[:110])
    except Exception as e:
        return (model, "ERR", str(e)[:80])

with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
    for m, s, info in ex.map(probe, MODELS):
        print(f"{s:8s} {m:22s} {info}")
