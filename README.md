# octopusx-farm

Массовая авторегистрация octopusx.ai (902+ аккаунта, 2 ключа/акк, $0.83 wallet)
+ self-hosted OpenAI-шлюз :16433 с farm-loop чейном.

**Полный гайд: [FARM_GUIDE.md](FARM_GUIDE.md)** — архитектура, все фиксы с
коммитами, метрики батчей, словарь ошибок, процедуры рестарта/пуша/мониторинга,
физика лимитов mail.tm.

Быстрый старт:
```bash
powershell -NoProfile -ExecutionPolicy Bypass -File octopusx_swap.ps1
timeout 150 python ox_farm_start.py
grep -E "alive|done|TOTAL" octopusx_autoreg.log | tail
```

Репозиторий: https://github.com/TopDeckhandBlock/octopusx-farm
Секреты (PAT) НЕ в этой папке: `C:/Users/User/tmp/gh_pats_repoonly.json`
