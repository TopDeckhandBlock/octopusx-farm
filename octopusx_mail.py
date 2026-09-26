import json, urllib.request, re, sys, time

ADDR = "oxbldyp25c@uberip.com"
PWD = "PF24XVwfedRF"

def req(url, data=None, method=None, hdr=None):
    h = {"Content-Type": "application/json"}
    if hdr: h.update(hdr)
    r = urllib.request.Request(url, data=json.dumps(data).encode() if data else None, headers=h, method=method)
    return json.loads(urllib.request.urlopen(r, timeout=20).read())

tok = req("https://api.mail.tm/token", {"address": ADDR, "password": PWD}, "POST")["token"]
H = {"Authorization": f"Bearer {tok}"}

for i in range(30):
    msgs = req("https://api.mail.tm/messages", hdr=H)["hydra:member"]
    if msgs:
        m = req(f"https://api.mail.tm/messages/{msgs[0]['id']}", hdr=H)
        text = m.get("text") or ""
        print("SUBJECT:", m.get("subject"))
        print("FROM:", m.get("from", {}).get("address"))
        print("BODY:", text[:800])
        codes = re.findall(r"\b(\d{4,8})\b", text)
        print("CODES:", codes)
        sys.exit(0)
    time.sleep(2)
print("NO MAIL after 60s")
