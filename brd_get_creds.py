"""brd_get_creds.py — pull ALL zone passwords via /users/get_customer (fresh cookies)."""
import json, urllib.request, urllib.error, sys
sys.path.insert(0, r"C:\Users\User\tmp")
try:
    from brd_cookies import COOKIE_HDR, XSRF
except ImportError:
    raise SystemExit('Create brd_cookies.py with your panel session: COOKIE_HDR, XSRF (see brd_cookies.example.py)')

BASE = "https://brightdata.com"
CID = "hl_2e228c6c"
HDRS = {
    "Cookie": COOKIE_HDR,
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "X-XSRF-TOKEN": XSRF,
    "X-Requested-With": "XMLHttpRequest",
    "Origin": BASE,
    "Referer": BASE + "/cp/zones",
}


def get(path):
    r = urllib.request.Request(BASE + path, headers=HDRS)
    try:
        resp = urllib.request.urlopen(r, timeout=40)
        return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="ignore")[:200]
    except Exception as e:
        return -1, f"{type(e).__name__}: {str(e)[:100]}"


st, cust = get(f"/users/get_customer?product=lum&customer={CID}")
print("get_customer status:", st)
if not isinstance(cust, dict):
    print("resp:", cust)
    sys.exit(1)

zones = cust.get("zones") or {}
print(f"\nZONES: {len(zones)}\n")
out = {}
for name, z in zones.items():
    pws = z.get("password") or []
    pw = pws[0] if pws else None
    plan = z.get("plan") or {}
    product = plan.get("product") or plan.get("type")
    out[name] = {"password": pw, "product": product, "plan_type": plan.get("type"),
                 "created": z.get("created"), "ips": z.get("ips")}
    print(f"  {name:22s} product={product:14s} pw={pw}")

# also try per-zone info for any zone missing a password
for name in zones:
    if not out[name]["password"]:
        st2, z2 = get(f"/users/get_zone_info?customer_id={CID}&product=lum&zone={name}")
        if isinstance(z2, dict):
            pws = z2.get("password") or []
            if pws:
                out[name]["password"] = pws[0]
                print(f"  [filled] {name} pw={pws[0]}")

json.dump(out, open(r"C:\Users\User\tmp\brd_creds.json", "w", encoding="utf-8"), indent=1)
print("\nsaved -> brd_creds.json")

# Build proxy strings
print("\n=== PROXY STRINGS ===")
for name, z in out.items():
    if not z["password"]:
        continue
    prod = z["product"]
    if prod in ("browser_api",):
        port = 9222
        proto = "wss"
    else:
        port = 22225
        proto = "http"
    cred = f"brd-customer-{CID}-zone-{name}-pass-{z['password']}"
    print(f"  {name} ({prod}):")
    print(f"    {proto}://{cred}@brd.superproxy.io:{port}")
