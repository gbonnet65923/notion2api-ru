# Notion2API-RU

> Notion AI → OpenAI-совместимый API + авторег аккаунтов

Реверс веб-интерфейса Notion AI, обёрнутый в стандартный `/v1/chat/completions`. Работает с Cherry Studio, Zotero, LobeChat и любым OpenAI-совместимым клиентом.

**Главная фишка этой сборки — встроенный авторег:** не нужно руками регистрировать аккаунты и дёргать токены из F12. `tools/farm.py` сам регистрирует новые аккаунты Notion через временные почты (voidash/mail.tm), проходит онбординг, выбирает модель и складывает готовые креды в пул.

## Возможности

- **OpenAI-совместимость** — `/v1/chat/completions`, стриминг (SSE) и обычные ответы
- **23 модели** — Claude (включая Opus 5), GPT-6 Astra, GPT-5.x, Gemini, Kimi, Grok, DeepSeek, GLM, Fable
- **Панель Thinking** — показывает рассуждения модели
- **Панель Search** — поисковые запросы и источники
- **Пул аккаунтов** — Round-Robin балансировка, cooldown при сбоях
- **Авторег** — ферма аккаунтов через временные почты, без капчи
- **Web UI** — встроенная панель, тёмная тема, анимации
- **Docker** — деплой одной командой

## Быстрый старт

### Вариант 1 — Авторег (рекомендую)

```bash
# ставим зависимости
pip install -r requirements.txt
pip install playwright httpx
playwright install chromium

# регистрируем 5 аккаунтов с Opus 5.5
python tools/farm.py 5 Opus
```

Ферма сама:
1. Создаёт временный ящик (voidash.bond или mail.tm)
2. Регистрирует аккаунт Notion, ловит код подтверждения из письма
3. Проходит онбординг (без карты, триал не нужен — модели доступны сразу)
4. Заходит в AI-чат, выбирает модель (Opus 5.5 / GPT-6.1 Sol / Kimi K3 / GPT-6 Luna)
5. Отправляет тестовое сообщение и проверяет ответ
6. Сохраняет креды в `farm_accounts.jsonl` + state-файл сессии

```bash
# конвертируем пул фермы в accounts.json для сервера
python tools/farm.py --export
```

### Вариант 2 — Ручные креды

```bash
python login.py          # откроет браузер, ждёт логина, сам вытащит token_v2 и всё остальное
```

Или руками через F12: Application → Cookies → `token_v2`, потом скрипт `scripts/extract_notion_info.js` в консоли — он выдаст все поля для `accounts.json`.

### Запуск сервера

```bash
pip install -r requirements.txt
uvicorn app.server:app --host 0.0.0.0 --port 8000
```

Или Docker:

```bash
docker-compose build --no-cache && docker-compose up -d
```

## Использование API

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8000/v1", api_key="any")

r = client.chat.completions.create(
    model="claude-opus5",
    messages=[{"role": "user", "content": "Привет"}],
    stream=True,
)
for chunk in r:
    print(chunk.choices[0].delta.content or "", end="")
```

| Эндпоинт | Метод | Описание |
|---|---|---|
| `/v1/chat/completions` | POST | Основной |
| `/v1/models` | GET | Список моделей |
| `/health` | GET | Статус пула аккаунтов |
| `/` | GET | Web UI |

## Режимы

| | Lite | Standard | Heavy |
|---|---|---|---|
| Память | нет | клиент | сервер |
| База | нет | нет | SQLite |
| Thinking/Search | нет | да | да |
| RPS | 30/мин | 25/мин | 20/мин |

`APP_MODE=standard` в `.env` — рекомендуемый.

## Модели

`claude-opus5`, `claude-sonnet4.6`, `claude-sonnet5`, `gpt-6-astra`, `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna`, `gemini-3.1pro`, `kimi-2.7`, `grok-4.3`, `deepseek-v4pro`, `glm-5.2`, `fable-5` и другие. Полный список: `GET /v1/models`.

## Переменные окружения

| Переменная | Описание | По умолчанию |
|---|---|---|
| `NOTION_ACCOUNTS` | JSON-массив кредов Notion | обязателен |
| `APP_MODE` | `lite` / `standard` / `heavy` | `heavy` |
| `API_KEY` | Bearer для клиентов | нет |
| `PORT` | Порт | 8000 |
| `SILICONFLOW_API_KEY` | Для сжатия контекста в Heavy | нет |

## Заметки

- Лимиты Notion: 5-часовой квоты тратятся быстро, месячной — медленно. Пул аккаунтов распределяет нагрузку.
- При 429 — добавить аккаунтов (`python tools/farm.py 5`).
- Ключи и `accounts.json` в `.gitignore` — не коммитить.

## Лицензия

MIT
