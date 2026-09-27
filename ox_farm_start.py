"""Start the big farm batch: n=500, workers=50 (target 100k via farm loop)."""
import json
import os
import urllib.request

N = int(os.environ.get("OX_N", "500"))
W = int(os.environ.get("OX_W", "50"))

req = urllib.request.Request("http://127.0.0.1:16433/api/autoreg/start",
                             data=json.dumps({"n": N, "workers": W}).encode(), method="POST")
req.add_header("Content-Type", "application/json")
try:
    with urllib.request.urlopen(req, timeout=120) as r:
        print(json.loads(r.read()))
except Exception as e:
    # GIL-slow spawn: request may have actually succeeded — verify state
    print("start call:", e)
    with urllib.request.urlopen("http://127.0.0.1:16433/api/autoreg/status", timeout=30) as r:
        print(json.loads(r.read()))