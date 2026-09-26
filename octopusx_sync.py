"""Sync keys from octopusx_accounts.jsonl into the octopusx rotator config (hot-reload)."""
import json
import os
import tempfile

JSONL = "octopusx_accounts.jsonl"
CFG = "octopusx_keys.json"

accs = [json.loads(l) for l in open(JSONL, encoding="utf-8") if l.strip()]
keys = list(dict.fromkeys(k for a in accs for k in a["keys"]))

cfg = {"keys": [], "base_url": "https://octopusx.ai/v1"}
if os.path.exists(CFG):
    with open(CFG, encoding="utf-8-sig") as f:
        cfg = json.load(f)
old = set(cfg.get("keys") or [])
merged = list(dict.fromkeys([*(cfg.get("keys") or []), *keys]))
cfg["keys"] = merged
cfg.setdefault("current_index", 0)
# keep stats/current_index etc; atomic write
fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(CFG)), suffix=".tmp")
with os.fdopen(fd, "w", encoding="utf-8") as f:
    json.dump(cfg, f, indent=2)
os.replace(tmp, CFG)
print(f"accounts={len(accs)} new={len(set(keys) - old)} total_keys={len(merged)} -> {CFG}")
