"""OctopusX (octopusx.ai) autoreg — mail.tm -> email-code login -> API keys with routing enabled.

Endpoints (new-api fork, JWT Bearer, no captcha):
  POST /app/verification          {"email":..., "purpose":"login"}
  POST /app/user/login/code       {"email":..., "code":..., "utm":"aix","utm_target":"aix"} -> JWT
  GET  /app/team/{team_id}/project/                       -> default project id
  POST /app/token/                {"project_id":...,"name":...,"allow_pay_mode":0,...} -> sk-key
  GET  /app/token/groups                                     -> model catalog for routing
  PUT  /app/token/                route config (strategy "default", all models) -> key becomes USABLE
  GET  /app/user/self                                          -> wallet.quota (600000 == $1)
Without the PUT the key answers "Invalid provider configuration for this token".

Usage: python octopusx_autoreg.py [N_ACCOUNTS] [KEYS_PER_ACCOUNT]
"""
import json
import random
import re
import string
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE = "https://octopusx.ai"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36")
ACCOUNTS_FILE = "octopusx_accounts.json"
QUOTA_PER_USD = 600_000

N_ACCOUNTS = int(sys.argv[1]) if len(sys.argv) > 1 else 5
KEYS_PER_ACCOUNT = int(sys.argv[2]) if len(sys.argv) > 2 else 2


def http(url, data=None, headers=None, method=None, timeout=45):
    h = {
        "User-Agent": UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US",
        "Origin": BASE if "octopusx" in url else "https://api.mail.tm",
    }
    if "octopusx" in url:
        h["Referer"] = BASE + "/console/"
    if data is not None:
        h["Content-Type"] = "application/json;charset=UTF-8"
    if headers:
        h.update(headers)
    req = urllib.request.Request(
        url, data=json.dumps(data).encode() if data is not None else None,
        headers=h, method=method or ("POST" if data is not None else "GET"))
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def rnd(n):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


class MailTm:
    def __init__(self):
        dom = http("https://api.mail.tm/domains")["hydra:member"][0]["domain"]
        self.address = "ox" + rnd(8) + "@" + dom
        self.password = rnd(14)
        http("https://api.mail.tm/accounts", {"address": self.address, "password": self.password}, method="POST")
        self.token = http("https://api.mail.tm/token",
                          {"address": self.address, "password": self.password}, method="POST")["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def wait_code(self, sender="octopusx.ai", timeout=90):
        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(3)
            msgs = http("https://api.mail.tm/messages", headers=self.headers)["hydra:member"]
            for m in msgs:
                if sender in (m.get("from", {}).get("address") or ""):
                    body = http(f"https://api.mail.tm/messages/{m['id']}",
                                headers=self.headers).get("text", "")
                    found = re.findall(r"\b(\d{6})\b", body)
                    if found:
                        return found[0]
        raise TimeoutError(f"no code for {self.address}")


def get_wallet(auth):
    return http(f"{BASE}/app/user/self", headers=auth)["data"]["wallet"]["quota"]


def register_account(i):
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
    assert r["data"]["login_meta"].get("is_new_user"), "not a new user?!"

    team_id = user["default_team_id"]
    project_id = http(f"{BASE}/app/team/{team_id}/project/", headers=auth)["data"][0]["id"]

    # model catalog for routing
    groups = http(f"{BASE}/app/token/groups", headers=auth)["data"]["strategies"]
    custom = next(s for s in groups if s["key"] == "custom")
    models = [{"id": m["id"], "enabled": True} for m in custom["models"]]

    wallet_start = get_wallet(auth)

    keys, wallet_end = [], wallet_start
    for k in range(KEYS_PER_ACCOUNT):
        r = http(f"{BASE}/app/token/", {
            "project_id": project_id, "name": f"k{k + 1}", "allow_pay_mode": 0,
            "spend_quota": 0, "unlimited_quota": True, "quota_refresh": "never",
        }, headers=auth)
        assert r.get("code") == 0, f"token create: {r}"
        tok = r["data"]
        # enable routing -> key becomes usable (fixes "Invalid provider configuration")
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
        wallet_end = get_wallet(auth)

    acc = {
        "email": email,
        "mail_password": box.password,
        "user_id": user["id"],
        "team_id": team_id,
        "project_id": project_id,
        "jwt": jwt,
        "keys": keys,
        "wallet_usd_start": round(wallet_start / QUOTA_PER_USD, 2),
        "wallet_usd_end": round(wallet_end / QUOTA_PER_USD, 2),
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    print(f"[{i}] {email} uid={user['id']} wallet ${acc['wallet_usd_start']} -> ${acc['wallet_usd_end']} "
          f"keys={len(keys)} {keys[0][:18]}...", flush=True)
    return acc


def main():
    accounts = []
    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = {ex.submit(register_account, i + 1): i for i in range(N_ACCOUNTS)}
        for f in as_completed(futs):
            try:
                accounts.append(f.result())
            except Exception as e:
                print(f"[!] failed: {type(e).__name__}: {e}", flush=True)
    with open(ACCOUNTS_FILE, "w", encoding="utf-8") as fh:
        json.dump(accounts, fh, indent=2, ensure_ascii=False)
    print(f"\nsaved {len(accounts)} accounts -> {ACCOUNTS_FILE}")
    for a in accounts:
        for k in a["keys"]:
            print(k)


if __name__ == "__main__":
    main()
