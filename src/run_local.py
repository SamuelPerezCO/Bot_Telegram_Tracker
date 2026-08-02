"""Local entry point of the tracker bot (t.me/Tracker90Bot).

Runs the bot in polling mode, which is the comfortable way to develop on
a local machine. In production the bot lives on Vercel as a serverless
webhook instead (see api/webhook.py), so this file is not used there.

This file must NOT be called main.py: Vercel scans for reserved names
(main.py, app.py, index.py, server.py, at the root or inside src/) and
would deploy this polling script as if it were the web app, which fails
and answers 500 on every route.

Telegram does not allow polling and a webhook at the same time. If the
webhook is already set, remove it first:

    python scripts/set_webhook.py delete

Streaks are stored in each chat's pinned message (see Models.streak_model),
so no database is needed.
"""

from telegram import Update

from bot import build_application


if __name__ == "__main__":
    build_application().run_polling(allowed_updates=Update.ALL_TYPES)


"""
URL of the BOT:
t.me/Tracker90Bot
"""
