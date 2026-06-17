# Ataman HR Bot (Telegram)

Чатбот для **массового первичного отбора** менеджеров по продажам (БАД): быстрый скрининг, отсев, запись на собеседование, напоминания. Демо в Telegram; продакшен WhatsApp — фаза 2.

## Принципы под высокую текучку

- **Сначала regex** — анкета «имя, возраст, студент, опыт» без LLM в типичных кейсах.
- **Жёсткий отсев в коде** — возраст, город, график, казахский; LLM не решает «подходит/нет».
- **Together AI** только для разбора нестандартного ввода и редких FAQ.
- **Кнопки** — меньше печати, быстрее запись на собес.
- **HR получает уведомление** только по подходящим, записанным и эскалациям (не на каждое сообщение).
- **`/admin/stats`** — счётчики воронки (started, qualified, rejected, scheduled).

## Старт: вид → язык → анкета

После `/start` три шага:

1. **Вид** — Telegram (кнопки) или WhatsApp (цифры 1/2): `1` / `2` или кнопки
2. **Язык** — Қазақша / Русский: `1` / `2` или кнопки (в WA-виде — только цифры)
3. **Анкета** — имя, возраст, студент, опыт и дальше скрининг

## Локальный запуск

```bash
cd ataman-hr-bot
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# заполнить TELEGRAM_BOT_TOKEN, TOGETHER_API_KEY, TELEGRAM_HR_CHAT_ID
uvicorn app.main:app --reload --port 8000
```

Webhook локально: ngrok → `WEBHOOK_BASE_URL` → `curl https://YOUR_URL/setup`

## Vercel

```bash
export VERCEL_TOKEN=...
chmod +x scripts/deploy-vercel.sh
./scripts/deploy-vercel.sh
```

Переменные в Vercel: см. `.env.example`.

**Напоминания:** на Hobby Vercel cron — раз в сутки. Для точных напоминаний за 2 ч вызывайте `GET /api/cron/reminders?secret=CRON_SECRET` каждые 15 мин (cron-job.org / Uptime Robot).

## Тест-кейсы для демо заказчику

1. **Подходит:** `Айым, 25, жоқ, жоқ` → Алматы → график иә → казахский иә → меню → запись.
2. **Отказ возраст:** `Данияр, 32, жоқ, жоқ`.
3. **Студент гибкий:** студент + «дүйсенбі сабақ, қалған күндері бос» → график келеді.

## Тесты

```bash
pytest -q
```
