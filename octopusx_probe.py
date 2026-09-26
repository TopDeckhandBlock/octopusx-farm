import json, urllib.request, concurrent.futures

BASE = "https://octopusx.ai/v1"
KEY = "sk-CK0qxUL4ldJWlLAQPcPfJzVSs8iQ7E4g7288bxTj2M7zGpLk"
HDR = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}

MODELS = [
    "gpt-3.5-turbo", "gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini", "gpt-5", "gpt-5-mini",
    "o1", "o3", "o3-mini", "o4-mini",
    "claude-3-5-sonnet-20241022", "claude-sonnet-4", "claude-sonnet-4-5", "claude-opus-4", "claude-opus-4-5", "claude-haiku-4",
    "gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash",
    "grok-2", "grok-3", "grok-4", "grok-beta",
    "deepseek-chat", "deepseek-reasoner", "deepseek-v3", "deepseek-v3.1",
    "qwen-max", "qwen-plus", "qwen-turbo", "qwen2.5-72b-instruct",
    "glm-4", "glm-4.5", "glm-4.6",
    "llama-3.3-70b", "llama-3.1-70b", "meta-llama/Llama-3.3-70B-Instruct",
    "mistral-large", "mistral-small",
    "kimi-k2", "moonshot-v1-8k",
    "yi-large", "ernie-4.0", "hunyuan-large", "minimax-text-01",
    "doubao-pro-32k", "command-r-plus",
]

def probe(model):
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 5}).encode()
    req = urllib.request.Request(f"{BASE}/chat/completions", data=body, headers=HDR, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            d = json.loads(r.read())
            content = (d.get("choices") or [{}])[0].get("message", {}).get("content", "")
            real = d.get("model", "?")
            return (model, "OK", f"upstream_model={real} reply={content!r}")
    except urllib.error.HTTPError as e:
        try:
            detail = e.read()[:200].decode(errors="replace")
        except Exception:
            detail = str(e)
        return (model, f"HTTP {e.code}", detail)
    except Exception as e:
        return (model, "ERR", str(e)[:120])

results = []
with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
    for res in ex.map(probe, MODELS):
        results.append(res)

ok = [r for r in results if r[1] == "OK"]
dead = [r for r in results if r[1] != "OK"]
print(f"=== ANSWERING: {len(ok)} ===")
for m, s, info in ok:
    print(f"  {m:40s} {s:6s} {info}")
print(f"=== NOT ANSWERING: {len(dead)} ===")
codes = {}
for m, s, info in dead:
    codes.setdefault(s, []).append(m)
for code, ms in codes.items():
    print(f"  {code}: {', '.join(ms)}")
