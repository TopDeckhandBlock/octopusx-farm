# 🐙 OctopusX Farm — фарм аккаунтов + свой OpenAI-шлюз

Фарм-система для [octopusx.ai](https://octopusx.ai): массовая авт регистрация
аккаунтов (подарочные кредиты на каждом: $5 или ~$1 — решает апстрим, рандом
на аккаунт; без капчи на регистрации) +
self-hosted OpenAI-совместимый шлюз с ротацией ключей, кулдаунами, дашбордом
и панелью управления авторегом.

Всё на чистом Python stdlib — ни одной зависимости. Один файл сервера.

## Что внутри

| Файл | Назначение |
|---|---|
| `octopusx_server.py` | **Шлюз + дашборд + управление авторегом** — один файл, stdlib-only, порт 16433 |
| `octopusx_batch200.py` | Пакетная регистрация аккаунтов (N аккаунтов, W воркеров) |
| `octopusx_alive.py` | Проверка живости каждого ключа (GET /models каждым ключом) |
| `octopusx_autoreg.py` | Регистрация одного аккаунта (mail.tm OTP → JWT → 2 ключа) |
| `octopusx_mail.py` | Клиент mail.tm (домен `uberip.com`, бесплатно, без капчи) |
| `octopusx_keys.py` | Выпуск ключей + обязательный route-config PUT |
| `octopusx_models.py` | Получение каталога моделей |
| `octopusx_sweep.py` | Прогон-тест всех моделей → `octopusx_sweep.json` |
| `octopusx_sync.py` | Пересборка пула ключей из accounts.jsonl |
| `octopusx_catalog.json`, `octopusx_sweep.json` | Каталог и вердикты (без секретов) |

## Быстрый старт

```bash
# 1. скопируй примеры и заполни своими данными (секретов в репе нет)
cp octopusx_accounts.jsonl.example octopusx_accounts.jsonl
cp octopusx_keys.json.example octopusx_keys.json

# 2. запусти сервер
python octopusx_server.py
```

Дашборд: **http://127.0.0.1:16433/**

Переменные окружения: `OCTOPUSX_PORT` (по умолчанию 16433), `OCTOPUSX_KEYS`
(путь к keys-json, по умолчанию рядом с файлом).

## Регистрация аккаунтов (авторег)

1. Берётся свежий ящик на **mail.tm** (публичное API, домен `uberip.com`) —
   бесплатно, без капчи.
2. OTP-код приходит через `POST /app/verification`, логин — через
   `POST /app/user/login/code`.
3. Выпускаются 2 API-ключа через `POST /app/token/` + **обязательный**
   `PUT /app/token/` route-config (без него 403).
4. Каждый аккаунт = подарочные кредиты ($5 или ~$1, рандом) + 2 API-ключа.
Запуск пачки: кнопка **▶ Start** в дашборде (аккаунты × воркеры) или напрямую:
`python octopusx_batch200.py 50 5` (50 аккаунтов, 5 воркеров).

## Шлюз (OpenAI-совместимый)

| Роут | Что делает |
|---|---|
| `GET /` | дашборд: статистика пула, таблица моделей с кнопками теста, лог запросов |
| `GET /health` | health-check |
| `GET /api/stats` | статистика пула + статус авторега + лог запросов |
| `GET /api/models` | каталог моделей + вердикты sweep + live-статистика |
| `GET /api/keys` | ключи (маскированные) + статус кулдаунов |
| `POST /api/probe` | `{"model": "gpt-5.5"}` — живой тест одной модели |
| `POST /api/autoreg/start` | `{"n": 10, "workers": 5}` — запустить регистрацию |
| `GET /api/autoreg/status` | прогресс + хвост лога |
| `POST /api/autoreg/stop` | убить текущий батч |
| `POST /api/autoreg/sync` | пересобрать пул ключей + hot-reload |
| `POST /v1/chat/completions` | **OpenAI-совместимый прокси**: ротация ключей, кулдауны (503→3с, 429→10с, quota→60с, 401→24ч), SSE-стриминг |

Подключается как обычный OpenAI endpoint:
`base_url = http://127.0.0.1:16433/v1`, любой Bearer-токен.

## Проверено на ферме 200 аккаунтов / 400 ключей

- **400/400 ключей живые** (проверка каждого ключа, см. `octopusx_alive.py`)
- Рабочие модели (34): gpt-5.5, gpt-5.6-sol, gpt-5.6-terra, gpt-5.4,
  gpt-6-astra, gpt-4o-mini, claude-opus-4-5/4-6/4-7/4-8/5,
  claude-sonnet-4-6/5, claude-haiku-4-5, claude-fable-5, deepseek-v4-flash,
  deepseek-v4.1-flash, семейство gemini-2.5/3.x, omni-1.1-flash(-v2v)
- Мёртвые на стороне апстрима: glm-5.3, kimi-k3, grok-4, семейство MiniMax (503)
- Итого $1000+ подарочных кредитов (бонус $5 или ~$1 на акк, рандом; фарм
  продолжается — живой счётчик в дашборде)

## Гайд по воспроизведению

1. **Форк/клон** репы, скопируй `.example`-файлы (структура данных описана
   прямо в них).
2. **Зарегистрируй первый аккаунт руками** через [mail.tm](https://mail.tm)
   и [octopusx.ai](https://octopusx.ai) — убедишься, что флоу живой.
3. **Прогони батч**: `python octopusx_batch200.py 10 3` — 10 аккаунтов для
   проверки.
4. **Синкни ключи** в дашборде (кнопка ⟳ Sync keys) или
   `python octopusx_sync.py`.
5. **Поднимай шлюз**: `python octopusx_server.py` → дашборд на :16433.
6. **Проверь ключи**: `python octopusx_alive.py` → `octopusx_alive.json`.
7. **Подключай** куда угодно как OpenAI-совместимый API.

## Лицензия / дисклеймер

Код для образовательных и research-целей. Автор не отвечает за использование.
