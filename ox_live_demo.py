"""LIVE demo: register accounts right now, print each one as it lands."""
import sys, time
sys.argv = ["octopusx_batch200.py", "10", "8"]
import octopusx_batch200 as B
from concurrent.futures import ThreadPoolExecutor, as_completed

B.N_ACCOUNTS, B.WORKERS = 10, 8
before = len([l for l in open(B.JSONL, encoding="utf-8") if l.strip()])
print(f"LIVE: pool=48 (user's 10 first) | accounts before: {before} | spawning 10 regs @ 8 workers", flush=True)

t0 = time.time()
ok = 0
with ThreadPoolExecutor(max_workers=8) as ex:
    futs = [ex.submit(B.register_with_retry, i + 1) for i in range(10)]
    for f in as_completed(futs):
        try:
            acc = f.result()
            if not acc or not acc.get("keys"):
                raise ValueError("register_with_retry returned no account/keys")
            ok += 1
            dt = time.time() - t0
            print(f"  + LIVE OK  {acc['email']}  ${acc['wallet_usd']}  keys={len(acc['keys'])}  {acc['keys'][0][:14]}...  [{dt:.0f}s]", flush=True)
        except Exception as e:
            print(f"  - LIVE FAIL {type(e).__name__}: {str(e)[:90]}  [{time.time()-t0:.0f}s]", flush=True)

after = len([l for l in open(B.JSONL, encoding="utf-8") if l.strip()])
print(f"\nRESULT: {before} -> {after} (+{after-before}) in {time.time()-t0:.0f}s", flush=True)
if after > before:
    last = [l for l in open(B.JSONL, encoding="utf-8") if l.strip()][-1]
    import json
    d = json.loads(last)
    keys = d.get("keys") or []
    print("newest key for gateway test:", (keys[0][:20] + "...") if keys else "<no keys>")