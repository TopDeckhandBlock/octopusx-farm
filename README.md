# OctopusX Farm

Mass-registration farm + self-hosted OpenAI-compatible gateway for
[octopusx.ai](https://octopusx.ai) ($5 gift credit per fresh account, no
captcha at signup).

## What's inside

| File | Purpose |
|---|---|
| `octopusx_server.py` | Single-file **gateway + dashboard + autoreg control** (stdlib only, port 16433) |
| `octopusx_batch200.py` | Batch account registration (N accounts, W workers) |
| `octopusx_alive.py` | Per-key alive check (GET /models with every key) |
| `octopusx_autoreg.py` | Single account registration flow (mail.tm OTP → JWT → 2 keys) |
| `octopusx_mail.py` | mail.tm client (domain `uberip.com`, free, no captcha) |
| `octopusx_keys.py` | Key issuance + mandatory route-config PUT |
| `octopusx_models.py` | Model catalog fetch |
| `octopusx_sweep.py` | Sweep-test all models, write `octopusx_sweep.json` |
| `octopusx_sync.py` | Re-sync key pool from accounts.jsonl |
| `octopusx_catalog.json` / `octopusx_sweep.json` | Catalog + sweep verdicts (no secrets) |

## Setup

```bash
cp octopusx_accounts.jsonl.example octopusx_accounts.jsonl   # your data
cp octopusx_keys.json.example octopusx_keys.json             # your data
python octopusx_server.py
```

Env: `OCTOPUSX_PORT` (default 16433), `OCTOPUSX_KEYS` (path to keys json,
default next to the file).

## Gateway routes

- `GET  /` — dashboard: pool stats, model table with per-model test buttons,
  autoreg control panel, request log
- `GET  /health`, `/api/stats`, `/api/models`, `/api/keys`
- `POST /api/probe` `{"model": "gpt-5.5"}` — live single-model test
- `POST /api/autoreg/start` `{"n": 10, "workers": 5}` → runs batch registration
- `GET  /api/autoreg/status`, `POST /api/autoreg/stop`, `POST /api/autoreg/sync`
- `POST /v1/chat/completions` (+ `/v1/models`) — OpenAI-compatible proxy with
  key rotation and cooldowns (503→3s, 429→10s, quota→60s, 401→24h)

Use it as a normal OpenAI endpoint: `base_url http://127.0.0.1:16433/v1`,
any Bearer.

## Verified on a 200-account / 400-key farm

- 400/400 keys alive (per-key GET /models, see `octopusx_alive.py`)
- Working models (34): gpt-5.5, gpt-5.6-sol, gpt-5.6-terra, gpt-5.4,
  gpt-6-astra, gpt-4o-mini, claude-opus-4-5/4-6/4-7/4-8/5,
  claude-sonnet-4-6/5, claude-haiku-4-5, claude-fable-5,
  deepseek-v4-flash, deepseek-v4.1-flash, gemini-2.5/3.x family,
  omni-1.1-flash(-v2v)
- Dead upstream: glm-5.3, kimi-k3, grok-4, MiniMax family (503)
- $1000 total gift credits ($5 × 200 accounts)

## Mail provider

mail.tm (public API, domain `uberip.com`) — free, no captcha. OTP arrives via
`POST /app/verification`, login via `POST /app/user/login/code`, keys via
`POST /app/token/` + mandatory `PUT /app/token/` route-config (403 without it).

## Legal

Educational/security research purposes. Respects nothing but rate limits.
