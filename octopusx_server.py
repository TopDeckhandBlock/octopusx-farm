#!/usr/bin/env python3
"""OctopusX Farm server: key-pool gateway + dashboard + autoreg control.

Single-file, stdlib-only. Serves:
  GET  /                      dashboard (HTML)
  GET  /health                minimal health (compat)
  GET  /api/stats             pool stats + autoreg status + request log
  GET  /api/models            catalog + sweep verdicts + live per-model stats
  GET  /api/keys              masked keys with cooldown status
  POST /api/probe             {"model": "..."} live single-model test
  POST /api/autoreg/start     {"n": 10, "workers": 5} -> runs octopusx_batch200.py
  GET  /api/autoreg/status    progress + log tail
  POST /api/autoreg/stop      kill running batch
  POST /api/autoreg/sync      run octopusx_sync.py + hot-reload pool
  *    /v1/*                  OpenAI-compatible proxy (rotation, cooldowns, SSE)

Env: OCTOPUSX_PORT (16433), OCTOPUSX_KEYS (octopusx_keys.json next to this file).
"""

from __future__ import annotations

import collections
import http.server

import json
import os
import ssl
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KEYS_PATH = os.environ.get("OCTOPUSX_KEYS", os.path.join(BASE_DIR, "octopusx_keys.json"))
ACCOUNTS_PATH = os.path.join(BASE_DIR, "octopusx_accounts.jsonl")
SWEEP_PATH = os.path.join(BASE_DIR, "octopusx_sweep.json")
BATCH_SCRIPT = os.path.join(BASE_DIR, "octopusx_batch200.py")
SYNC_SCRIPT = os.path.join(BASE_DIR, "octopusx_sync.py")
LOG_PATH = os.path.join(BASE_DIR, "octopusx_autoreg.log")

HOST = os.environ.get("OCTOPUSX_HOST", "127.0.0.1")
PORT = int(os.environ.get("OCTOPUSX_PORT", "16433"))
MAX_BODY_BYTES = 10 * 1024 * 1024
UPSTREAM_TIMEOUT = 180
PROBE_TIMEOUT = 90
REQLOG_SIZE = 300
FARM_LOOP = os.environ.get("OCTOPUSX_FARM_LOOP") == "1"
FARM_TARGET = int(os.environ.get("OCTOPUSX_FARM_TARGET", "0") or 0)

lock = threading.RLock()
state: dict = {
    "keys": [], "base": "", "upstream_headers": {},
    "cooldowns": {}, "idx": 0, "ok": 0, "fail": 0,
    "last_error": None, "started": time.time(), "config_mtime": 0.0,
    "model_stats": {},          # model -> {ok, fail, last, ts, ms}
    "reqlog": collections.deque(maxlen=REQLOG_SIZE),
}
catalog_cache: dict = {"ts": 0.0, "models": []}
accounts_cache: dict = {"mtime": 0.0, "n": 0, "wallet": 0.0}

autoreg: dict = {
    "running": False, "proc": None, "n": 0, "workers": 5,
    "started": None, "finished": None, "exit_code": None,
    "accounts_before": 0, "syncing": False, "last_sync": None,
    "loop_stop": False,
}

ctx = ssl.create_default_context()


# ---------------------------------------------------------------- config ----
def load_config() -> None:
    with open(KEYS_PATH, encoding="utf-8-sig") as f:
        cfg = json.load(f)
    keys = cfg.get("keys") or []
    if isinstance(keys, list) and keys and isinstance(keys[0], dict):
        keys = [k.get("key") or k.get("api_key") for k in keys if k.get("key") or k.get("api_key")]
    base = cfg.get("base_url") or cfg.get("baseUrl") or ""
    if base and not base.startswith("http"):
        base = "https://" + base
    with lock:
        state["keys"] = [k for k in keys if k]
        if base:
            state["base"] = base.rstrip("/")
        state["upstream_headers"] = cfg.get("upstream_headers") or cfg.get("headers") or {}
        state["config_mtime"] = os.path.getmtime(KEYS_PATH)
        state["idx"] = state["idx"] % max(len(state["keys"]), 1)
    print(f"[cfg] keys={len(state['keys'])} base={state['base']}", flush=True)


def maybe_hot_reload() -> None:
    try:
        m = os.path.getmtime(KEYS_PATH)
        if m != state["config_mtime"]:
            load_config()
    except OSError:
        pass


def accounts_info() -> dict:
    try:
        m = os.path.getmtime(ACCOUNTS_PATH)
        if m == accounts_cache["mtime"]:
            return accounts_cache
        n, wallet = 0, 0.0
        with open(ACCOUNTS_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                n += 1
                try:
                    wallet += float(json.loads(line).get("wallet_usd") or 0)
                except (ValueError, json.JSONDecodeError):
                    pass
        accounts_cache.update(mtime=m, n=n, wallet=round(wallet, 2))
    except OSError:
        pass
    return accounts_cache


# ------------------------------------------------------------- pool logic ----
def sweep_verdicts() -> dict:
    out: dict[str, dict] = {}
    try:
        with open(SWEEP_PATH, encoding="utf-8") as f:
            for e in json.load(f):
                name = (e.get("model") or "").strip().strip('"')
                if name:
                    out[name] = e
    except (OSError, json.JSONDecodeError):
        pass
    return out


def select_key(tried: set) -> str | None:
    maybe_hot_reload()
    now = time.time()
    with lock:
        keys = list(state["keys"])
        cds = state["cooldowns"]
        for k in list(cds):
            if cds[k] <= now:
                del cds[k]
        avail = [k for k in keys if k not in tried and k not in cds]
        if not avail:
            avail = [k for k in keys if k not in tried]
        if not avail:
            return None
        key = avail[state["idx"] % len(avail)]
        state["idx"] += 1
        return key


def mark_cooldown(key: str, code: int, body: bytes | None) -> None:
    err = ""
    if body:
        try:
            d = json.loads(body)
            e = d.get("error", {}) if isinstance(d, dict) else {}
            err = f"{e.get('code', '')} {e.get('message', '')}".lower()
        except Exception:
            err = body.decode("utf-8", "ignore").lower()
    dur = 5
    if "arrearage" in err or "good standing" in err:
        dur = 1800
    elif "invalid" in err or "incorrect api key" in err or code == 401:
        dur = 86400
    elif "quota" in err:
        dur = 60
    elif code == 429:
        dur = 10
    elif code in (500, 502, 503, 504):
        dur = 3
    with lock:
        state["cooldowns"][key] = time.time() + dur


def is_retryable(code: int, body: bytes | None) -> bool:
    if code in (408, 429, 500, 502, 503, 504):
        return True
    if body:
        try:
            d = json.loads(body)
            msg = (d.get("error", {}).get("message", "") if isinstance(d, dict) else "").lower()
            return any(w in msg for w in ("channel", "rate", "timeout", "upstream", "try again"))
        except Exception:
            return False
    return False


def mask_key(k: str) -> str:
    return f"{k[:9]}...{k[-4:]}" if len(k) > 16 else k[:4] + "..."


def record(model: str, ok: bool, status: str, ms: int, key: str) -> None:
    with lock:
        st = state["model_stats"].setdefault(model, {"ok": 0, "fail": 0, "last": "", "ts": 0, "ms": 0})
        st["ok" if ok else "fail"] = st["ok" if ok else "fail"] + 1
        st["last"], st["ts"], st["ms"] = status, time.time(), ms
        state["ok" if ok else "fail"] += 1
        if ok:
            state["last_error"] = None
        else:
            state["last_error"] = status
        state["reqlog"].append({
            "ts": time.time(), "model": model, "ok": ok, "status": status,
            "ms": ms, "key": mask_key(key),
        })


# --------------------------------------------------------------- upstream ----
def upstream_request(method: str, path: str, body: bytes | None, key: str):
    if state["base"].endswith("/v1") and path.startswith("/v1/"):
        path = path[3:]
    url = state["base"] + path
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Authorization", f"Bearer {key}")
    req.add_header("Content-Type", "application/json")
    for hk, hv in state["upstream_headers"].items():
        req.add_header(hk, hv)
    return urllib.request.urlopen(req, timeout=UPSTREAM_TIMEOUT, context=ctx)


def probe_model(model: str) -> dict:
    maybe_hot_reload()
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": "Say OK"}],
                       "max_tokens": 8}).encode()
    tried: set = set()
    total = len(state["keys"])
    t0 = time.time()
    for _ in range(min(max(total, 1), 4)):
        key = select_key(tried)
        if not key:
            break
        tried.add(key)
        try:
            with upstream_request("POST", "/v1/chat/completions", body, key) as r:
                data = json.loads(r.read() or b"{}")
                content = ""
                try:
                    content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "") or ""
                except Exception:
                    pass
                ms = int((time.time() - t0) * 1000)
                record(model, True, "OK", ms, key)
                return {"model": model, "status": "OK", "content": content[:120], "ms": ms}
        except urllib.error.HTTPError as e:
            eb = e.read()
            if is_retryable(e.code, eb):
                mark_cooldown(key, e.code, eb)
                continue
            ms = int((time.time() - t0) * 1000)
            err = _err_text(eb)
            record(model, False, f"HTTP {e.code}", ms, key)
            return {"model": model, "status": f"HTTP {e.code}", "error": err[:200], "ms": ms}
        except Exception as e:
            mark_cooldown(key, 0, None)
            continue
    ms = int((time.time() - t0) * 1000)
    record(model, False, "no key / upstream fail", ms, "—")
    return {"model": model, "status": "FAIL", "error": "all attempts failed", "ms": ms}


def _err_text(b: bytes) -> str:
    try:
        d = json.loads(b)
        e = d.get("error", {}) if isinstance(d, dict) else {}
        return str(e.get("message") or b.decode("utf-8", "ignore"))
    except Exception:
        return b.decode("utf-8", "ignore") if b else ""


def upstream_catalog() -> list:
    now = time.time()
    if now - catalog_cache["ts"] < 60 and catalog_cache["models"]:
        return catalog_cache["models"]
    maybe_hot_reload()
    tried: set = set()
    for _ in range(min(max(len(state["keys"]), 1), 3)):
        key = select_key(tried)
        if not key:
            break
        tried.add(key)
        try:
            with upstream_request("GET", "/v1/models", None, key) as r:
                d = json.loads(r.read() or b"{}")
                arr = d.get("data") if isinstance(d, dict) else d
                models = sorted({(m.get("id") or "?") if isinstance(m, dict) else str(m) for m in (arr or [])})
                catalog_cache.update(ts=now, models=models)
                return models
        except Exception:
            continue
    return catalog_cache.get("models", [])


# ---------------------------------------------------------------- autoreg ----
def autoreg_start(n: int, workers: int) -> dict:
    with lock:
        if autoreg["running"] or (autoreg["proc"] and autoreg["proc"].poll() is None):
            return {"error": "already running"}
        if not os.path.exists(BATCH_SCRIPT):
            return {"error": f"missing {os.path.basename(BATCH_SCRIPT)}"}
        autoreg.update(running=True, n=n, workers=workers, started=time.time(),
                       finished=None, exit_code=None, loop_stop=False,
                       accounts_before=accounts_info().get("n", 0))
        log = open(LOG_PATH, "ab")
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        autoreg["proc"] = subprocess.Popen(
            [sys.executable, "-u", BATCH_SCRIPT, str(n), str(workers)],
            cwd=BASE_DIR, stdout=log, stderr=subprocess.STDOUT, creationflags=flags)
        threading.Thread(target=_autoreg_watch, daemon=True).start()
    return {"started": True, "n": n, "workers": workers, "pid": autoreg["proc"].pid}


def _autoreg_watch() -> None:
    p = autoreg["proc"]
    code = p.wait()
    with lock:
        autoreg.update(running=False, finished=time.time(), exit_code=code)
    try:
        subprocess.run([sys.executable, "-u", SYNC_SCRIPT], cwd=BASE_DIR,
                       capture_output=True, timeout=120,
                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        with lock:
            autoreg["last_sync"] = time.time()
    except Exception:
        pass
    if FARM_LOOP and not autoreg.get("loop_stop"):
        try:
            n_acc = accounts_info().get("n", 0)
            if FARM_TARGET and n_acc >= FARM_TARGET:
                print(f"[farm-loop] target {FARM_TARGET} reached ({n_acc}), stopping", flush=True)
                return
            autoreg_start(autoreg["n"] or 10, autoreg["workers"] or 5)
            print(f"[farm-loop] next batch n={autoreg['n']} (accounts {n_acc}/{FARM_TARGET or '∞'})", flush=True)
        except Exception as e:
            print(f"[farm-loop] chain failed: {e}", flush=True)

def autoreg_stop() -> dict:
    with lock:
        autoreg["loop_stop"] = True
        p = autoreg["proc"]
        if p and p.poll() is None:
            p.kill()
            return {"stopped": True}
        return {"error": "not running"}


def autoreg_sync() -> dict:
    with lock:
        if autoreg["syncing"]:
            return {"error": "sync already running"}
        autoreg["syncing"] = True
    try:
        r = subprocess.run([sys.executable, "-u", SYNC_SCRIPT], cwd=BASE_DIR,
                           capture_output=True, timeout=120,
                           creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        maybe_hot_reload()
        with lock:
            autoreg["last_sync"] = time.time()
        return {"synced": True, "exit": r.returncode,
                "out": r.stdout.decode("utf-8", "ignore")[-200:]}
    except Exception as e:
        return {"error": str(e)}
    finally:
        with lock:
            autoreg["syncing"] = False


def autoreg_status() -> dict:
    with lock:
        p = autoreg["proc"]
        alive = bool(p and p.poll() is None)
        lines: list[str] = []
    try:
        with open(LOG_PATH, "rb") as f:
            lines = f.read().decode("utf-8", "ignore").splitlines()[-12:]
    except OSError:
        pass
    acc = accounts_info()
    with lock:
        return {
            "running": alive, "n": autoreg["n"], "workers": autoreg["workers"],
            "started": autoreg["started"], "finished": autoreg["finished"],
            "exit_code": autoreg["exit_code"],
            "accounts_before": autoreg["accounts_before"],
            "accounts_now": acc.get("n", 0), "log": lines,
            "syncing": autoreg["syncing"], "last_sync": autoreg["last_sync"],
        }


# ------------------------------------------------------------------ routes ----
def api_stats() -> dict:
    acc = accounts_info()
    with lock:
        cds = {mask_key(k): int(v - time.time()) for k, v in state["cooldowns"].items() if v > time.time()}
        return {
            "status": "ok", "port": PORT,
            "keys": len(state["keys"]), "cooldowns": len(cds),
            "cooldown_detail": cds,
            "ok": state["ok"], "fail": state["fail"], "idx": state["idx"],
            "last_error": state["last_error"],
            "uptime_s": int(time.time() - state["started"]),
            "accounts": acc.get("n", 0), "wallet_usd": acc.get("wallet", 0.0),
            "models_working": sum(1 for v in sweep_verdicts().values() if v.get("status") == "OK"),
            "autoreg": autoreg_status(),
            "reqlog": list(state["reqlog"])[-30:],
        }


def api_models() -> list:
    sweep = sweep_verdicts()
    cat = upstream_catalog()
    with lock:
        stats = {k: dict(v) for k, v in state["model_stats"].items()}
    names = sorted(set(cat) | set(sweep) | set(stats))
    out = []
    for n in names:
        s = stats.get(n, {})
        sw = sweep.get(n, {})
        out.append({
            "name": n,
            "sweep": sw.get("status") or ("unknown" if not sw else sw.get("status")),
            "live_ok": s.get("ok", 0), "live_fail": s.get("fail", 0),
            "last": s.get("last", ""), "ms": s.get("ms", 0), "ts": s.get("ts", 0),
        })
    return out


def api_keys() -> list:
    now = time.time()
    with lock:
        cds = dict(state["cooldowns"])
        return [{"key": mask_key(k),
                 "cooldown_s": int(cds[k] - now) if cds.get(k, 0) > now else 0}
                for k in state["keys"]]


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a) -> None:
        pass

    def _json(self, obj: object, code: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html", "/dashboard"):
            self._html(DASHBOARD_HTML)
        elif self.path in ("/health", "/v1/health"):
            with lock:
                self._json({"status": "ok", "keys": len(state["keys"]),
                            "cooldowns": len(state["cooldowns"]), "port": PORT,
                            "ok": state["ok"], "fail": state["fail"],
                            "last_error": state["last_error"]})
        elif self.path == "/api/stats":
            self._json(api_stats())
        elif self.path == "/api/models":
            self._json(api_models())
        elif self.path == "/api/keys":
            self._json(api_keys())
        elif self.path == "/api/autoreg/status":
            self._json(autoreg_status())
        else:
            self._proxy("GET")

    def do_POST(self) -> None:
        if self.path == "/api/probe":
            d = self._read_json()
            m = (d or {}).get("model", "").strip()
            if not m:
                self._json({"error": "model required"}, 400)
            else:
                self._json(probe_model(m))
        elif self.path == "/api/autoreg/start":
            d = self._read_json() or {}
            n = max(1, min(int(d.get("n", 10)), 500))
            w = max(1, min(int(d.get("workers", 5)), 20))
            self._json(autoreg_start(n, w))
        elif self.path == "/api/autoreg/stop":
            self._json(autoreg_stop())
        elif self.path == "/api/autoreg/sync":
            self._json(autoreg_sync())
        else:
            self._proxy("POST")

    def _read_json(self) -> dict | None:
        try:
            n = int(self.headers.get("Content-Length", 0))
            if not n or n > MAX_BODY_BYTES:
                return None
            return json.loads(self.rfile.read(n))
        except Exception:
            return None

    # ------------------------------------------------------------ proxy ----
    def _proxy(self, method: str) -> None:
        path = self.path
        if path.startswith("/v1/"):
            path = path[3:]
        elif path == "/v1":
            path = "/"
        with lock:
            base, total = state["base"], len(state["keys"])
        if not base:
            self._json({"error": "no base_url configured"}, 503)
            return
        body = None
        model = ""
        if method == "POST":
            length = int(self.headers.get("Content-Length", 0))
            if length > MAX_BODY_BYTES:
                self._json({"error": "payload too large"}, 413)
                return
            body = self.rfile.read(length) if length else None
            if body:
                try:
                    model = json.loads(body).get("model", "")
                except Exception:
                    pass

        t0 = time.time()
        tried: set = set()
        attempts = 0
        while attempts < min(max(total, 1), 4):
            key = select_key(tried)
            if not key:
                break
            tried.add(key)
            attempts += 1
            try:
                resp = upstream_request(method, path, body, key)
            except urllib.error.HTTPError as e:
                eb = e.read()
                if is_retryable(e.code, eb):
                    mark_cooldown(key, e.code, eb)
                    if attempts < max(total, 1):
                        continue
                record(model or path, False, f"HTTP {e.code}", int((time.time() - t0) * 1000), key)
                self._json({"error": {"message": _err_text(eb) or f"HTTP {e.code}",
                                      "type": "upstream_error", "code": e.code}}, e.code)
                return
            except Exception as e:
                mark_cooldown(key, 0, None)
                if attempts >= min(max(total, 1), 4):
                    record(model or path, False, f"conn: {type(e).__name__}", int((time.time() - t0) * 1000), key)
                    self._json({"error": {"message": f"upstream conn: {e}", "type": "conn_error"}}, 502)
                    return
                continue
            try:
                ctype = resp.headers.get("Content-Type", "application/json")
                self.send_response(resp.status)
                self.send_header("Content-Type", ctype)
                self.send_header("Access-Control-Allow-Origin", "*")
                if "text/event-stream" in ctype.lower():
                    self.send_header("Cache-Control", "no-cache")
                    self.send_header("X-Accel-Buffering", "no")
                    self.send_header("Transfer-Encoding", "chunked")
                else:
                    self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()

                def w(b: bytes) -> None:
                    self.wfile.write(b"%x\r\n" % len(b) + b + b"\r\n")
                    self.wfile.flush()

                try:
                    if "text/event-stream" in ctype.lower():
                        while True:
                            line = resp.readline()
                            if not line:
                                break
                            w(line)
                    else:
                        while True:
                            chunk = resp.read(65536)
                            if not chunk:
                                break
                            w(chunk)
                except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
                    pass
                self.wfile.write(b"0\r\n\r\n")
                record(model or path, True, "OK", int((time.time() - t0) * 1000), key)
            finally:
                try:
                    resp.close()
                except Exception:
                    pass
            return
        self._json({"error": "pool exhausted (no key available)"}, 503)


# -------------------------------------------------------------- dashboard ----
DASHBOARD_HTML = r"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<title>OctopusX Farm</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--bg:#0a0e14;--p:#121821;--b:#1d2733;--t:#c9d6e3;--m:#7d8ca0;--a:#4cc2ff;--ok:#3fb950;--bad:#f85149;--warn:#d29922}
*{box-sizing:border-box}
body{margin:0;padding:20px;font:14px/1.5 "Segoe UI",system-ui,sans-serif;background:var(--bg);color:var(--t)}
h1{margin:0;font-size:19px}h1 span{color:var(--a)}
.sub{color:var(--m);font-size:12px;margin:2px 0 18px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;margin-bottom:18px}
.card{background:var(--p);border:1px solid var(--b);border-radius:10px;padding:12px 16px}
.card .v{font-size:24px;font-weight:700;color:var(--a)}.card .v.ok{color:var(--ok)}.card .v.bad{color:var(--bad)}.card .v.warn{color:var(--warn)}
.card .l{font-size:11px;color:var(--m);text-transform:uppercase;letter-spacing:.6px;margin-top:2px}
.panel{background:var(--p);border:1px solid var(--b);border-radius:10px;padding:14px 16px;margin-bottom:16px}
.panel h2{margin:0 0 10px;font-size:15px;color:var(--t)}
.row{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
input,select{background:var(--bg);border:1px solid var(--b);color:var(--t);border-radius:8px;padding:7px 10px;font-size:13px;width:90px}
input.wide{width:220px}
button{background:#16324a;border:1px solid #2a4d6b;color:var(--a);border-radius:8px;padding:7px 14px;font-size:13px;cursor:pointer}
button:hover{background:#1c4266}button:disabled{opacity:.4;cursor:default}
button.sm{padding:3px 10px;font-size:12px}
.tag{display:inline-block;padding:1px 8px;border-radius:6px;font-size:11px;font-weight:600}
.tag.ok{background:#0f2e18;color:var(--ok);border:1px solid #1c5429}
.tag.bad{background:#2e120f;color:var(--bad);border:1px solid #54211c}
.tag.warn{background:#2e2410;color:var(--warn);border:1px solid #544721}
.tag.mut{background:#151b24;color:var(--m);border:1px solid var(--b)}
table{width:100%;border-collapse:collapse;font-size:12.5px}
th{color:var(--m);text-align:left;font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.5px;padding:6px 8px;border-bottom:1px solid var(--b)}
td{padding:6px 8px;border-bottom:1px solid #141b25}
tr:hover td{background:#0e141d}
.mono{font-family:Consolas,monospace;font-size:12px}
#mlog{max-height:340px;overflow-y:auto}
.log{background:var(--bg);border:1px solid var(--b);border-radius:8px;padding:8px 10px;font:11.5px/1.5 Consolas,monospace;color:var(--m);max-height:150px;overflow-y:auto;white-space:pre-wrap}
.foot{color:var(--m);font-size:11px;text-align:right;margin-top:6px}
.err{background:#25171c;border:1px solid #5c2a2e;color:var(--bad);border-radius:8px;padding:8px 12px;margin-bottom:14px;font-size:12.5px}
.bar{height:8px;background:var(--bg);border:1px solid var(--b);border-radius:6px;overflow:hidden;margin-top:8px}
.bar i{display:block;height:100%;background:var(--a)}
</style></head><body>
<h1>🐙 OctopusX <span>Farm</span> <span style="font-size:13px;color:var(--m)">:__PORT__</span></h1>
<div class="sub">gateway · key pool · autoreg — auto-refresh 5s</div>
<div class="err" id="err" style="display:none"></div>
<div class="grid" id="cards"></div>

<div class="panel"><h2>Autoreg</h2>
<div class="row">
accounts <input id="a-n" type="number" value="10" min="1" max="500">
workers <input id="a-w" type="number" value="5" min="1" max="20">
<button id="a-start">▶ Start</button>
<button id="a-stop">■ Stop</button>
<button id="a-sync">⟳ Sync keys</button>
<span id="a-state" class="tag mut">idle</span>
</div>
<div class="bar" id="a-bar" style="display:none"><i id="a-fill" style="width:0%"></i></div>
<div class="log" id="a-log" style="margin-top:8px">—</div>
</div>

<div class="panel"><h2>Models <span id="m-count" class="tag mut"></span></h2>
<div class="row" style="margin-bottom:10px">
<input class="wide" id="m-q" placeholder="filter…">
<select id="m-f"><option value="">all</option><option value="ok">working (sweep)</option><option value="dead">dead</option><option value="live">live-tested</option></select>
<span class="sub" id="m-note"></span>
</div>
<div id="mlog"><table><thead><tr><th>Model</th><th>Sweep</th><th>Live</th><th>Last</th><th>Latency</th><th></th></tr></thead><tbody id="m-rows"></tbody></table></div>
</div>

<div class="panel"><h2>Requests</h2>
<table><thead><tr><th>Time</th><th>Model</th><th>Status</th><th>Latency</th><th>Key</th></tr></thead><tbody id="r-rows"></tbody></table>
</div>

<div class="panel"><h2>Keys (masked) <span id="k-count" class="tag mut"></span></h2>
<div id="k-rows" style="max-height:200px;overflow-y:auto" class="mono"></div>
</div>

<script>
const $=id=>document.getElementById(id);
const fmt=s=>{s=+s||0;return s>86400?Math.round(s/86400)+'d':s>3600?Math.round(s/3600)+'h':s>60?Math.round(s/60)+'m':s+'s'};
const ago=t=>t?fmt((Date.now()/1000)-t)+' ago':'—';
function esc(s){return String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
function tag(cls,txt){return '<span class="tag '+cls+'">'+esc(txt)+'</span>'}

function stats(){
 fetch('/api/stats').then(r=>r.json()).then(s=>{
  $('cards').innerHTML=[
   ['Keys',s.keys,''],['Cooldowns',s.cooldowns,s.cooldowns?'warn':''],['OK',s.ok,'ok'],['Fail',s.fail,s.fail?'bad':''],
   ['Accounts',s.accounts,''],['Wallet $',s.wallet_usd,''],['Models OK',s.models_working,'ok'],['Uptime',fmt(s.uptime_s),'']
  ].map(c=>'<div class="card"><div class="v '+c[2]+'">'+esc(c[1])+'</div><div class="l">'+c[0]+'</div></div>').join('');
  if(s.last_error){$('err').style.display='block';$('err').textContent='last_error: '+s.last_error}else $('err').style.display='none';
  $('a-state').className='tag '+(s.autoreg.running?'ok':'mut');
  $('a-state').textContent=s.autoreg.running?'running ('+(s.autoreg.accounts_now-s.autoreg.accounts_before)+'/'+s.autoreg.n+')':(s.autoreg.exit_code!==null&&s.autoreg.exit_code!==undefined?'exit '+s.autoreg.exit_code:'idle');
  if(s.autoreg.running&&s.autoreg.n){$('a-bar').style.display='block';$('a-fill').style.width=Math.min(100,100*(s.autoreg.accounts_now-s.autoreg.accounts_before)/s.autoreg.n)+'%'}
  else $('a-bar').style.display='none';
  if(s.autoreg.log&&s.autoreg.log.length)$('a-log').textContent=s.autoreg.log.slice(-8).join('\n');
  $('r-rows').innerHTML=(s.reqlog||[]).slice().reverse().map(r=>'<tr><td class="mono">'+new Date(r.ts*1000).toLocaleTimeString()+'</td><td>'+esc(r.model)+'</td><td>'+(r.ok?tag('ok','OK'):tag('bad',r.status))+'</td><td class="mono">'+r.ms+'ms</td><td class="mono">'+esc(r.key)+'</td></tr>').join('');
  if(s.cooldown_detail&&Object.keys(s.cooldown_detail).length)$('k-rows').innerHTML=Object.entries(s.cooldown_detail).map(([k,v])=>'<div>'+esc(k)+' '+tag('warn',fmt(v))+'</div>').join('');
  else $('k-rows').textContent='no active cooldowns';
  $('k-count').textContent=s.keys+' keys';
 }).catch(e=>{$('err').style.display='block';$('err').textContent='stats: '+e});
}

function models(){
 fetch('/api/models').then(r=>r.json()).then(list=>{
  const q=$('m-q').value.toLowerCase(),f=$('m-f').value;
  let rows=list.filter(m=>{
   if(q&&!m.name.toLowerCase().includes(q))return false;
   if(f==='ok'&&m.sweep!=='OK')return false;
   if(f==='dead'&&m.sweep!=='HTTP 403'&&m.sweep!=='HTTP 503'&&m.sweep!=='HTTP 400')return false;
   if(f==='live'&&!(m.live_ok||m.live_fail))return false;
   return true});
  $('m-count').textContent=rows.length+' / '+list.length;
  const okn=list.filter(m=>m.sweep==='OK').length;
  $('m-note').textContent=okn+' working in sweep';
  $('m-rows').innerHTML=rows.map(m=>{
   const sw=m.sweep==='OK'?tag('ok','OK'):m.sweep==='unknown'?tag('mut','?'):tag('bad',m.sweep);
   const live=(m.live_ok||m.live_fail)?(m.live_fail&&!m.live_ok?tag('bad',m.live_fail+'F'):m.live_ok&&!m.live_fail?tag('ok',m.live_ok+' OK'):tag('warn',m.live_ok+'OK/'+m.live_fail+'F')):'<span style="color:var(--m)">—</span>';
   const last=m.last?(m.last==='OK'?tag('ok','OK'):tag('bad',m.last)):'<span style="color:var(--m)">—</span>';
   return '<tr><td class="mono">'+esc(m.name)+'</td><td>'+sw+'</td><td>'+live+'</td><td>'+last+'</td><td class="mono">'+(m.ms?m.ms+'ms':'')+'</td><td><button class="sm" onclick="probe(\''+esc(m.name).replace(/'/g,"")+'\')">test</button></td></tr>'}).join('');
 }).catch(e=>{$('err').style.display='block';$('err').textContent='models: '+e});
}

window.probe=function(name){
 const b=$('m-rows').querySelector('td.mono');document.title='⏳ '+name;
 fetch('/api/probe',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({model:name})})
  .then(r=>r.json()).then(j=>{document.title='OctopusX Farm';models()});
};

function aPost(url,body){return fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:body})
 .then(r=>r.json()).then(d=>{if(d.error){$('a-state').className='tag bad';$('a-state').textContent=d.error}else{stats()}})
 .catch(e=>{$('a-state').className='tag bad';$('a-state').textContent=String(e)})};
$('a-start').onclick=()=>aPost('/api/autoreg/start',JSON.stringify({n:+$('a-n').value||10,workers:+$('a-w').value||5}));
$('a-stop').onclick=()=>aPost('/api/autoreg/stop');
$('a-sync').onclick=()=>{$('a-sync').disabled=true;aPost('/api/autoreg/sync').then(()=>{$('a-sync').disabled=false})};
$('m-q').oninput=models;$('m-f').onchange=models;

stats();models();setInterval(stats,5000);setInterval(models,15000);
</script></body></html>""".replace("__PORT__", str(PORT))


def main() -> None:
    load_config()
    srv = http.server.ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"[octopusx-farm] http://{HOST}:{PORT}/ keys={len(state['keys'])}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
