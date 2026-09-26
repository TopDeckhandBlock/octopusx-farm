import json, urllib.request, concurrent.futures

KEY = "sk-egDLREROhdTYHCmwSssUFKzEdwjHfi2kEdpSyS2jCsTowNK3"
BASE = "https://octopusx.ai/v1"
HDR = {
    "Authorization": f"Bearer {KEY}",
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://octopusx.ai",
    "Referer": "https://octopusx.ai/console/",
}
MODELS = [
    "gpt-6-astra", "gpt-5.6-sol", "gpt-5.6", "gpt-6", "gpt-4o", "gpt-4o-mini", "gpt-4.1", "o4-mini", "o3",
    "claude-fable-5", "claude-sonnet-4-5", "claude-opus-4-5", "claude-haiku-4-5", "claude-sonnet-4",
    "gemini-3.1-pro", "gemini-3.1-flash", "gemini-2.5-pro", "gemini-2.5-flash",
    "deepseek-v4-pro", "deepseek-v4-flash", "deepseek-chat", "deepseek-reasoner",
    "glm-5.3", "glm-4.6", "kimi-k3", "kimi-k2", "qwen-max", "qwen3.8-max",
    "llama-3.3-70b", "mistral-large", "grok-4", "grok-4.6",
]

def probe(model):
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": "Say OK"}], "max_tokens": 8}).encode()
    req = urllib.request.Request(f"{BASE}/chat/completions", data=body, headers=HDR, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            d = json.loads(r.read())
            content = (d.get("choices") or [{}])[0].get("message", {}).get("content", "")
            return (model, "OK", f"{content!r}")
    except urllib.error.HTTPError as e:
        try:
            detail = e.read()[:150].decode(errors="replace")
        except Exception:
            detail = ""
        return (model, f"HTTP {e.code}", detail.replace("\n", " ")[:110])
    except Exception as e:
        return (model, "ERR", str(e)[:100])

results = []
with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
    for res in ex.map(probe, MODELS):
        results.append(res)
        if res[1] == "OK":
            print(f"LIVE  {res[0]:24s} {res[2][:60]}")

print("\n--- failures ---")
for m, s, info in results:
    if s != "OK":
        print(f"{s:8s} {m:24s} {info[:90]}")
