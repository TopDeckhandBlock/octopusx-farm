# OctopusX Farm — полный гайд

Массовая авторегистрация аккаунтов octopusx.ai (new-api форк) через бесплатные
HTTP-прокси + mail.tm temp-inbox. Каждый акк = 2 API-ключа, кошелёк ~$0.83.
Self-hosted OpenAI-шлюз на :16433 с дашбордом и farm-loop чейном.

- Репа: https://github.com/TopDeckhandBlock/octopusx-farm (публичная, без секретов)
- Рабочая папка: `C:/Users/User/tmp/` (пуш через REST API — git CLI сломан)
- Единый снапшот: `C:/Users/User/tmp/octopusx-farm/` (эта папка)
- Данные на 2026-09-28: **902 аккаунта, ~1700+ ключей**

## Архитектура

```
ox_farm_start.py ──POST /api/autoreg/start──▶ octopusx_server.py (:16433)
                                               │ farm-loop: spawn batch → ждёт → чейнит снова
                                               ▼
                            octopusx_batch200.py  N попыток × W воркеров
                                               │
              ┌────────────────────────────────┼────────────────────────────────┐
              ▼                                ▼                                ▼
   octopusx_proxies.py                MailTm (mail.tm)                  octopusx.ai API
   пул: SOURCES 25 листов             /domains (TTL-кеш 600s)           /app/verification
   fetch MAX×4=12000 → test           /accounts → /token                /app/user/login/code
   через mail.tm /domains             код из inbox (polling)            → keys ×2 → jsonl
   pick(): skip _dead + _mail_cd
```

## Файлы

### Ядро (production-цепочка)

| Файл | Роль |
|---|---|
| `octopusx_server.py` | OpenAI-шлюз :16433, дашборд, API клампы (n≤1000, workers≤60), `_autoreg_watch` farm-loop с чейном |
| `octopusx_batch200.py` | Регистратор: `http()` с 429-ветками, `_pick_proxy()` wait-for-fresh, `_mail_burn()`, `MailTm` с TTL-кешем домена, `register_account()` |
| `octopusx_proxies.py` | Пул: SOURCES (25 живых листов), MAX_PROXIES=3000, кандидаты ×4, `test_proxy()` через **mail.tm /domains**, `pick()` (skip dead+cooldown), `mark_mail_cd(1800s)`, `mail_cd_left()` |
| `ox_farm_start.py` | POST /api/autoreg/start 500×50 |
| `octopusx_swap.ps1` | Рестарт сервера (kill + spawn) |
| `octopusx_autostart.ps1` | Автозапуск стека |
| `gh_push_cd.py` | Пуш файлов в репо: PAT → GitHub Contents API (GET sha → PUT) |
| `ox_probe_mail.py` | Диагностика: mail.tm/mail.gw/OX через пул и direct |

### Данные

| Файл | Содержимое |
|---|---|
| `octopusx_accounts.jsonl` | 902 аккаунта (email, password, uid, keys, wallet) |
| `octopusx_keys.json` | dict `{keys: [sk-...]}` — все добытые ключи |
| `octopusx_proxies.json` | живой пул (123 mail.tm-рабочих прокси) |
| `octopusx_alive.json` | снапшот alive-прокси |
| `octopusx_autoreg.log` | лог батчей (паттерн `--- N/500 done, X acc/s, ETA Y min`) |
| `octopusx_catalog.json`, `octopusx_sweep.json` | каталог моделей и sweep-результаты |

### Утилиты

| Файл | Роль |
|---|---|
| `octopusx_keys.py` | Извлечение/валидация ключей |
| `octopusx_alive.py` | Alive-чек прокси |
| `octopusx_models.py`, `add_octopusx_models.py` | Каталог моделей, добавление в шлюз |
| `octopusx_diag.py`, `octopusx_probe.py`, `octopusx_retest.py` | Диагностика API |
| `octopusx_sweep.py`, `octopusx_sync.py`, `octopusx_tokinfo.py` | Sweep моделей, синк ключей, token info |
| `octopusx_restart_watch.py` | Вотчер перезапусков |
| `octopusx_mail.py`, `octopusx_variants.py`, `octopusx_pricing.py` | Mail-тесты, вариативные ручки, прайсинг |

Секрет (НЕ в папке, НЕ в репе): `C:/Users/User/tmp/gh_pats_repoonly.json` — PAT TopDeckhandBlock (repo scope).

## Фиксы сессии (эволюция yield)

| # | Фикс | Проблема | Решение | Коммит |
|---|---|---|---|---|
| 1 | Mail-cooldown | 451× `429 @ api.mail.tm/accounts` — per-IP квота; воркеры долбили сожжённые IP | `mark_mail_cd(p, 900s)` + `_mail_cd` реестр; `pick()` пропускает кулдаунные; `_mail_burn()` в обеих 429-ветках `http()` | `6cc73cf44d`, `db5367257d` |
| 2 | Server клампы | API позволял n>1000/workers>60 → самоубийство пула | Клампы в autoreg_start | `7c8e9b8434` |
| 3 | Пул caps | 92 живых из 6079 — мало ёмкости | MAX_PROXIES 2000→3000, кандидаты ×3→×4 (12000) → 160 живых | `6cc73cf44d` |
| 4 | Wait-for-fresh | pick() fallback «любой горячий» → 440/500 попыток сгорели в 429-пустоту | `_pick_proxy()`: 4×(15-25s) sleep пока все в кулдауне, cap ~80s, потом fallback | `4b8bc0febe`, `b6eebed210` |
| 5 | Cooldown 1800s | 900s мало при 8× oversubscription | `mark_mail_cd` дефолт 900→1800 | `b6eebed210` |
| 6 | mail.tm alive-check | alive-check через ipify: прокси «жив», но mail.tm банит ASN (Cloudflare) → `no mail provider answered /domains` | `TEST_URL = api.mail.tm/domains`, TIMEOUT 8→12: пул = только mail.tm-рабочие IP | `f0eec40561` |
| 7 | mail.gw drop | Зеркало мертво глобально (502 direct, timeout via proxy) — жгло 15s/попытку | `PROVIDERS = ["https://api.mail.tm"]` | `912cb16088` |
| 8 | TTL-кеш домена | GET /domains на КАЖДУЮ попытку × 50 воркеров × retries → сотни запросов с IP → Cloudflare бан (105× «no provider answered» mid-batch) | `_dom_cache` (ts, api, dom), TTL 600s, stale-cache fallback | (пуш следующим) |

### Метрики батчей

| Батч | Alive-пул | Yield | Акков | Примечание |
|---|---|---|---|---|
| mail_burn (49036) | 160/12087 | 12% первые 100 → ~0% к концу | 896 | cooldown 900, pick-any fallback жгёл конец батча |
| чейн B1 (убит) | 103/6079 | ~0.4% | 898 | старый код, 266×429 |
| wait-for-fresh (42140) | 65/12135 (ipify) | тонет | 899 | /domains-баны, мёртвый gw в PROVIDERS |
| mail.tm-check (44788) | 123/12055 | 2.5% старт | 899→902 | alive-check mail.tm, gw убран |
| TTL-кеш (35312) | 123+ | живые реги ($0.83 keys=2) | 902+ | /domains кеш 600s |

## Ошибки-словарь

| Ошибка | Значение | Действие |
|---|---|---|
| `429 @ api.mail.tm/accounts` (2877× за сессию) | Per-IP квота ящиков mail.tm (~1-2/час) | Авто: `_mail_burn` → cooldown 1800s → wait-for-fresh |
| `no mail provider answered /domains` | IP забанен Cloudflare на mail.tm или hammering /domains | Авто: TTL-кеш; alive-check фильтрует пул |
| `429 @ octopusx.ai/app/verification` | OX rate-limit | Авто: retry с ротацией прокси |
| `HTTP 422` | Невалидный адрес (НЕ rate-limit) | Не лечить как квоту |
| `HTTP 403` direct на octopusx.ai | OX банит прямой IP | Только через прокси |
| `mail.gw 502` direct | Зеркало мертво | Убран из PROVIDERS |

## Процедуры

### Рестарт фармы
```bash
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { \$_.CommandLine -like '*batch200*' -or \$_.CommandLine -like '*octopusx_server*' } | ForEach-Object { Stop-Process -Id \$_.ProcessId -Force }"
powershell -NoProfile -ExecutionPolicy Bypass -File octopusx_swap.ps1
timeout 150 python ox_farm_start.py   # ожидай {'started': True, 'n': 500, 'workers': 50}
```
**Процесс-паттерн**: каждый spawn = venv-trampoline (hermes python) + реальный (system python 3.11). Убивать ОБА по ParentProcessId. Порт 16433 слушает реальный python. GIL-quirk: ответ /api/autoreg/start может таймаутить — запрос проходит, проверь процессы.

### Мониторинг
```bash
grep -E "alive|done|TOTAL" octopusx_autoreg.log | tail -5
python -c "print('accounts:', len([l for l in open('octopusx_accounts.jsonl',encoding='utf-8') if l.strip()]))"
python -c "import octopusx_proxies as px; pool=px.load(); hot=[p for p in pool if px.mail_cd_left(p)>0]; print(f'pool {len(pool)}, hot {len(hot)}, fresh {len(pool)-len(hot)}')"
```
Внимание: `_mail_cd`/`_dead` — процесс-локальные. Из отдельного python -c они пусты; реальное состояние только в памяти batch-процесса.

### Пуш в репо
`gh_push_cd.py` — поменять FILES, запустить. PAT из `gh_pats_repoonly.json`, REST Contents API (GET sha → PUT {message, content, sha}).

### Диагностика mail
`python ox_probe_mail.py` — mail.tm/mail.gw/OX через 3 случайных прокси + direct.

## Потолок и физика лимитов

- mail.tm per-IP: ~1-2 аккаунта/час. Устойчивый yield = **alive pool × квота/час**.
- 123 mail.tm-рабочих IP ≈ 150-250 акк/час теоретический потолок (реально меньше из-за OX-429 и гниения прокси).
- Бесплатные прокси гниют: alive 160→65 за сутки. Валидация 12k кандидатов = ~13-15 мин.
- Прямой IP (Triolan + ZTE CGNAT 46.211.171.198) забанен mail.tm (timeout) и OX (403) — **только прокси**.
- ZTE-модем: RNDIS "Ethernet 2" (192.168.0.2), роуты mail.tm/mail.gw/api.mail.tm/ip-api.com через 192.168.0.1 оставлены. A/B-тест: mobile egress для mail.tm бесполезен (429 и там) — гипотеза опровергнута.
- Каждый акк: uid, $0.83 wallet, 2 ключа. Ключи → `octopusx_keys.json` → шлюз :16433.

## Известные проблемы

1. **Farm-loop чейнит мгновенно** после батча — пул не успевает восстановить mail-квоты (30 мин cooldown vs чейн через 0). Возможный фикс: пауза 20-30 мин между батчами.
2. **Репу пушим из tmp/**, снапшот-папка может отстать. Правило: после пуша — `cp` в `octopusx-farm/`.
3. **Роуг-дубли batch200** дуэлят jsonl/прокси-файлы. Правило: при рестарте убивать ВСЕ server|batch200 python-процессы, проверять топологию по ParentProcessId.
4. **LSP-шум** (Pyright urllib.error stubs) — рантайм работает, не чинить.
