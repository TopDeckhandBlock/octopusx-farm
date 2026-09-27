import json

# 10 user-verified proxies (front of pool = picked first via random, dedup)
USER = [
    "http://95.211.174.135:3128",
    "http://158.255.212.55:9090",
    "http://213.111.146.36:18080",
    "http://78.110.197.210:7080",
    "http://144.124.251.24:10088",
    "http://93.183.127.6:3128",
    "http://85.8.47.212:7080",
    "http://85.8.47.208:7080",
    "http://85.8.47.210:7080",
    "http://164.92.175.92:3128",
]

pool = json.load(open("C:/Users/User/tmp/octopusx_proxies.json", encoding="utf-8"))
before = len(pool)
merged = USER + [p for p in pool if p not in set(USER)]
json.dump(merged, open("C:/Users/User/tmp/octopusx_proxies.json", "w", encoding="utf-8"), indent=1)
print(f"pool: {before} -> {len(merged)} (user +10 injected first)")