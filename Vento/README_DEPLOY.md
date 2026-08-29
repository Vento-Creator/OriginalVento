# Vento — deployment

## Environment

Copy `.env.example` to `.env` and fill in the real values:

- `API_ID`
- `API_HASH`
- `BOT_TOKEN`
- `SUPER_ADMIN_ID`
- optional `SECOND_ADMIN_ID`
- optional `ADMIN_REPORT_CHAT_ID`

`config.py` no longer writes secrets to `config.json` and does not contain production credentials.

## Docker

```bash
cp .env.example .env
# edit .env
docker compose up -d --build
```

The `/app/data` volume keeps SQLite and Telegram sessions persistent across container restarts.

## Local

```bash
python -m pip install -r requirements.txt
python main.py
```

Never commit `.env`, Telegram session files, SQLite databases, or `config.json`.
