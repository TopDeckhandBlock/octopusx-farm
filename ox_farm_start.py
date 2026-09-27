"""Start the big farm batch: n=200, workers=30 (target 100k via farm loop)."""
import json, urllib.request

req = urllib.request.Request("http://127.0.0.1:16433/api/autoreg/start",
                             data=json.dumps({"n": 200, "workers": 30}).encode(), method="POST")
req.add_header("Content-Type", "application/json")
with urllib.request.urlopen(req, timeout=50) as r:
    print(json.loads(r.read()))