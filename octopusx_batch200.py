"""OctopusX batch: 200 accounts, 2 keys each, durable JSONL append.

Usage: python octopusx_batch200.py [N_ACCOUNTS] [WORKERS]
Appends each account to octopusx_accounts.jsonl immediately (crash-safe).
"""
import json
import random
import re
import string
import sys
import time
import urllib.error
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

_tls = threading.local()  # per-account proxy: _tls.proxy = "http://ip:port" or None

BASE = "https://octopusx.ai"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36")
JSONL = "octopusx_accounts.jsonl"
QUOTA_PER_USD = 600_000

N_ACCOUNTS = int(sys.argv[1]) if len(sys.argv) > 1 else 200
WORKERS = int(sys.argv[2]) if len(sys.argv) > 2 else 5


def http(url, data=None, headers=None, method=None, timeout=15, retries=3):
    for attempt in range(retries):
        try:
            h = {"User-Agent": UA, "Accept": "application/json, text/plain, */*",
                 "Accept-Language": "en-US",
                 "Origin": BASE if "octopusx" in url else
                           "https://" + urllib.parse.urlparse(url).netloc}
            if "octopusx" in url:
                h["Referer"] = BASE + "/console/"
            if data is not None:
                h["Content-Type"] = "application/json;charset=UTF-8"
            if headers:
                h.update(headers)
            req = urllib.request.Request(
                url, data=json.dumps(data).encode() if data is not None else None,
                headers=h, method=method or ("POST" if data is not None else "GET"))
            proxy = getattr(_tls, "proxy", None)
            if proxy:
                try:
                    opener = urllib.request.build_opener(urllib.request.ProxyHandler(
                        {"http": proxy, "https": proxy}))
                    with opener.open(req, timeout=timeout) as r:
                        return json.loads(r.read())
                except urllib.error.HTTPError as e:
                    # 429/502/503 via proxy = IP burned for THIS host, proxy is
                    # alive -> rotate WITHOUT killing it (mark_dead'ing here
                    # drained the whole pool during a single 429 storm)
                    if e.code in (429, 502, 503):
                        if ".mail.tm" in url or ".mail.gw" in url:
                            _mail_burn(proxy)  # per-IP quota: cool it, don't re-pick
                        if attempt < retries - 1:
                            _tls.proxy = _pick_proxy()
                            time.sleep(3 * (attempt + 1))
                            continue
                        raise RuntimeError(f"HTTP {e.code} @ {url}") from e
                    if attempt < retries - 1:
                        _rotate_dead(proxy)
                        continue
                    raise
                except Exception:
                    if attempt < retries - 1:
                        _rotate_dead(proxy)  # dead proxy -> mark dead + rotate
                        continue
                    raise
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code in (429, 502, 503) and attempt < retries - 1:
                if ".mail.tm" in url or ".mail.gw" in url:
                    _mail_burn(proxy)
                if proxy:  # IP burned for this host -> rotate (keep in pool)
                    _tls.proxy = _pick_proxy()
                time.sleep(3 * (attempt + 1))
                continue
            raise RuntimeError(f"HTTP {e.code} @ {url}") from e
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            raise


def rnd(n):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


class MailTm:
    """Temp inbox on mail.tm OR its mirror mail.gw (same API, split rate limits).
    Sticky failover: keep the provider that worked last, switch on failure."""
    PROVIDERS = ["https://api.mail.tm", "https://api.mail.gw"]
    _sticky = None  # class-level: last api that answered /domains

    def _pick_api(self):
        order = [p for p in self.PROVIDERS if p != self._sticky]
        if self._sticky:
            order.insert(0, self._sticky)
        else:
            random.shuffle(order)
        for api in order:
            try:
                dom = http(f"{api}/domains")["hydra:member"][0]["domain"]
                MailTm._sticky = api
                return api, dom
            except Exception:
                continue
        raise RuntimeError("no mail provider answered /domains")

    def __init__(self):
        self.api, dom = self._pick_api()
        self.address = random.choice(["james", "mary", "john", "linda", "robert", "michael", "sarah", "david", "karen", "emily","daniel", "jessica", "kevin", "laura", "brian", "amanda", "steve", "rachel", "paul", "anna"]) + rnd(random.randint(2, 5)) + "@" + dom
        self.password = rnd(14)
        http(f"{self.api}/accounts", {"address": self.address, "password": self.password}, method="POST")
        self.token = http(f"{self.api}/token",
                          {"address": self.address, "password": self.password}, method="POST")["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def wait_code(self, sender="octopusx", timeout=120):
        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(4)
            try:
                msgs = http(f"{self.api}/messages", headers=self.headers)["hydra:member"]
            except Exception:
                continue
            for m in msgs:
                if sender in (m.get("from", {}).get("address") or ""):
                    body = http(f"{self.api}/messages/{m['id']}",
                                headers=self.headers).get("text", "")
                    found = re.findall(r"\b(\d{6})\b", body)
                    if found:
                        return found[0]
        raise TimeoutError(f"no code for {self.address}")


def get_wallet(auth):
    return http(f"{BASE}/app/user/self", headers=auth)["data"]["wallet"]["quota"]


def register_account(i):
    _tls.proxy = _pick_proxy()
    box = MailTm()
    email = box.address

    r = http(f"{BASE}/app/verification", {"email": email, "purpose": "login"})
    assert r.get("code") == 0, f"verification: {r}"
    code = box.wait_code()
    r = http(f"{BASE}/app/user/login/code",
             {"email": email, "code": code, "utm": "aix", "utm_target": "aix"})
    assert r.get("code") == 0, f"login: {r}"
    user = r["data"]["user"]
    jwt = r["data"]["token"]
    auth = {"Authorization": f"Bearer {jwt}"}
    assert r["data"]["login_meta"].get("is_new_user"), "existing user?!"

    team_id = user["default_team_id"]
    project_id = http(f"{BASE}/app/team/{team_id}/project/", headers=auth)["data"][0]["id"]

    groups = http(f"{BASE}/app/token/groups", headers=auth)["data"]["strategies"]
    custom = next(s for s in groups if s["key"] == "custom")
    models = [{"id": m["id"], "enabled": True} for m in custom["models"]]

    keys = []
    for k in range(2):
        r = http(f"{BASE}/app/token/", {
            "project_id": project_id, "name": f"k{k + 1}", "allow_pay_mode": 0,
            "spend_quota": 0, "unlimited_quota": True, "quota_refresh": "never",
        }, headers=auth)
        assert r.get("code") == 0, f"token create: {r}"
        tok = r["data"]
        r = http(f"{BASE}/app/token/", {
            "token_id": tok["id"],
            "basic": {"name": f"k{k + 1}", "expire_type": "never", "expire_at": 0,
                      "expire_duration": 0, "allow_pay_mode": 0},
            "route": {"strategy": "default", "config": {"default": {"models": models}}},
            "quota": {"enabled": True, "cos_region": 0, "mj_mode": "", "mj_proxy_url": "",
                      "spend_quota": 0, "unlimited_quota": True, "quota_refresh": "never"},
            "access": {"enabled": False, "model_limits": [], "gemini_media_type": 0,
                       "is_prompt_extend": 0, "allow_ips": ""},
        }, headers=auth, method="PUT")
        assert r.get("code") == 0, f"route put: {r}"
        keys.append(tok["key"])

    acc = {
        "email": email, "mail_password": box.password,
        "user_id": user["id"], "team_id": team_id, "project_id": project_id,
        "jwt": jwt, "keys": keys,
        "wallet_usd": round(get_wallet(auth) / QUOTA_PER_USD, 2),
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(JSONL, "a", encoding="utf-8") as fh:  # crash-safe append
        fh.write(json.dumps(acc, ensure_ascii=False) + "\n")
    print(f"[{i}] {email} uid={user['id']} ${acc['wallet_usd']} keys={len(keys)} {keys[0][:16]}..",
          flush=True)
    return acc
def _pick_proxy():
    try:
        import octopusx_proxies
        return octopusx_proxies.pick()
    except Exception:
        return None

def _mail_burn(p):
    """mail 429 on this IP: 15-min cooldown in the shared pool."""
    try:
        import octopusx_proxies
        octopusx_proxies.mark_mail_cd(p)
    except Exception:
        pass
def _rotate_dead(p):
    """Mark proxy dead in the shared pool memory, then pick the next one."""
    try:
        import octopusx_proxies
        octopusx_proxies.mark_dead(p)
    except Exception:
        pass
    _tls.proxy = _pick_proxy()


def register_with_retry(i, attempts=5):

    for a in range(attempts):
        try:
            return register_account(i)
        except Exception:
            if a == attempts - 1:
                raise
            time.sleep(3 + 4 * (a + 1))

def main():
    try:
        import octopusx_proxies
        alive = octopusx_proxies.refresh()
        print(f"[proxies] using {len(alive)} free proxies (direct fallback per thread)")
    except Exception as e:
        print(f"[proxies] unavailable ({e}), going direct")
    done = 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = [ex.submit(register_with_retry, i + 1) for i in range(N_ACCOUNTS)]
        for f in as_completed(futs):
            done += 1
            try:
                f.result()
            except Exception as e:
                print(f"[!] {type(e).__name__}: {str(e)[:110]}", flush=True)
            if done % 10 == 0:
                rate = done / (time.time() - t0)
                print(f"--- {done}/{N_ACCOUNTS} done, {rate:.2f} acc/s, ETA {((N_ACCOUNTS - done) / rate) / 60:.1f} min", flush=True)
    n = sum(1 for _ in open(JSONL, encoding="utf-8"))
    print(f"\nTOTAL accounts in {JSONL}: {n}")


if __name__ == "__main__":
    main()
