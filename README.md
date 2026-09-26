# OctopusX Farm

Auto-registration farm for **OctopusX.ai** (new-api fork, $5 gift per account, no captcha) + local key-pool gateway.

## Results

| Metric | Value |
|---|---|
| Accounts | **200** (`octopusx_accounts.jsonl`, uid 1190–1392) |
| API keys | **400** (2 per account, unlimited quota) |
| Gift quota | **$1000** ($5.0/account) |
| Working models | **34 / 134** catalog models (see `octopusx_sweep.json`) |

## Registration flow (reverse-engineered)

No captcha, no phone. Per account ~15s:

1. **Mailbox** — `mail.tm` API (uberip.com domain), random local part.
2. **Request code** — `POST /app/verification` `{"email": "...", "purpose": "login"}`.
3. **Login by code** — `POST /app/user/login/code` `{"email", "code", "utm": "aix", "utm_target": "aix"}` → JWT.
4. **Team/project bootstrap** — auto via JWT'd `/app/*` calls.
5. **Keys** — `GET /app/token/groups` → `POST /app/token/` **×2** (1 regular + 1 with route config).
6. **Route config** — `PUT /app/token/` with route body, otherwise the key returns **403** on inference.
7. **Wallet** — $5.0 gift lands immediately.

Key quirks:
- mail.tm `429`s hard at 5+ workers → retries at the future level (see `register_with_retry`), not the loop level.
- The 2nd key **needs** the `PUT /app/token/` route-config call or every completion 403s.
- Browser-ish headers (`Origin/Referer/User-Agent`) required for the Cloudflare layer.

## Scripts

| File | Purpose |
|---|---|
| `octopusx_batch200.py` | Main farm: N accounts × 2 keys, retries, JSONL output |
| `octopusx_sync.py` | Merge accounts → `octopusx_keys.json` gateway config (400 keys) |
| `octopusx_sweep.py` | Probe every catalog model → `octopusx_sweep.json` (34 working) |
| `octopusx_autoreg.py` | Single-account flow prototype (the reverse-engineering artifact) |
| `octopusx_keys.py` | Key CRUD helpers (create/list/route-config via JWT) |
| `octopusx_mail.py` | mail.tm provider (mailbox create + OTP wait) |
| `octopusx_models.py` | Catalog fetch/parse helpers |
| `octopusx_pricing.py` | Pricing table fetch |
| `octopusx_probe.py` | Single-model inference probe |
| `octopusx_retest.py` | Re-test previously failed models |
| `octopusx_tokinfo.py` | Token group/info introspection |
| `octopusx_variants.py` | Model-name variant expansion for sweep |
| `octopusx_diag.py` | Misc diagnostics |

## Data files (sensitive — repo stays private)

- `octopusx_accounts.jsonl` — 200 accounts: email, mail password, user_id, team_id, project_id, JWT, 2× API key, wallet_usd, created.
- `octopusx_keys.json` — gateway config: 400 keys + `base_url` (`https://octopusx.ai/v1`) + browser `upstream_headers`.
- `octopusx_sweep.json` — per-model verdicts (34 working).
- `octopusx_catalog.json` — full model catalog snapshot.

## Gateway setup

`octopusx_keys.json` feeds any OpenAI-compatible key-rotating proxy. The farm's local rotator (not included here) exposes:

```
POST http://127.0.0.1:16433/v1/chat/completions   # any Authorization bearer
GET  http://127.0.0.1:16433/v1/models             # live upstream catalog
GET  http://127.0.0.1:16433/health                # keys/cooldowns/ok/fail
```

Key rotation: round-robin over 400 keys, per-key cooldowns (503→3s, 429→10s, quota→60s, 401→24h), hot-reload on config mtime. Upstream auth + browser headers injected server-side.

### OMP / any OpenAI client

```yaml
# provider entry
apiKey: anything
baseUrl: http://127.0.0.1:16433/v1
models: [claude-opus-4-8, gpt-5.5, gpt-6-astra, ...]
```

## Working models (34)

```
claude-fable-5, claude-haiku-4-5, claude-opus-4-5, claude-opus-4-6, claude-opus-4-7,
claude-opus-4-8, claude-opus-5, claude-sonnet-4-6, claude-sonnet-5,
deepseek-v4-flash, deepseek-v4.1-flash,
gemini-2.5-flash, gemini-2.5-flash-image, gemini-2.5-flash-lite, gemini-2.5-pro,
gemini-3-flash-preview, gemini-3-pro-image, gemini-3.1-flash-image, gemini-3.1-flash-lite,
gemini-3.1-flash-lite-image, gemini-3.1-flash-lite-preview, gemini-3.5-flash, gemini-3.5-flash-lite,
gemini-3.6-flash, gemini-3.7-flash, gemini-3.8-flash,
gpt-4o-mini, gpt-5.4, gpt-5.5, gpt-5.6-sol, gpt-5.6-terra, gpt-6-astra,
omni-1.1-flash, omni-1.1-flash-v2v
```

Known dead: `glm-5.3`, `kimi-k3`, `grok-4`, `MiniMax-*` (503 no channel), `claude-sonnet-4-5` (400 not priced), plus ~100 others. `gemini-3.8-flash` passes the sweep but intermittently 503s — flaky upstream.

## Usage

```bash
# register 200 accounts (2 keys each) -> octopusx_accounts.jsonl
python octopusx_batch200.py 200 2

# merge into gateway config
python octopusx_sync.py

# sweep all catalog models
python octopusx_sweep.py
```
