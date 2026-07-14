# Bot_Telegram_Tracker

A Telegram bot that tracks a daily streak for a personal goal. Report every day you keep the streak alive - miss a day and it restarts.

Bot: [t.me/Tracker90Bot](https://t.me/Tracker90Bot)

---

## Features

- Daily streak tracking per Telegram user
- Report a completed day (only counts once per day)
- Streak continues if you reported yesterday, restarts if you missed a day
- Reset your streak when you lose
- Check your friend's streak from your own chat
- Streak starts at 0 as soon as you `/start` the bot, so your friend can check it right away
- No database: the streak is stored in the chat's pinned message
- Your current streak is always visible at the top of the chat

---

## Requirements

- Python 3.14+
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- Server to run the bot

---

## Dependencies

```bash
pip install python-telegram-bot python-dotenv
```

---

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/SamuelPerezCO/Bot_Telegram_Tracker.git
   cd Bot_Telegram_Tracker
   ```
2. Install the dependencies (see above).
3. Create a `.env` file in the project root with your bot token and the chat id of each user:
   ```
   TOKEN_BOT=your_token_from_botfather
   CHAT_1 = CHAT_ID_1
   CHAT_2 = CHAT_ID_2
   ```
   To get a chat id, send `/id` to the bot - it replies with the number. This only needs to be done once per user.

---

## Usage

Run the bot:

```bash
cd src
python main.py
```

Then in Telegram:

1. Send `/start` to the bot.
2. Answer the "Who are you?" question - the bot shows your current streak (created at 0 on the first time).
3. Choose an option:
   - **I want to report a new day** -> adds today to your streak.
   - **I want to report that I lose** -> resets your streak to 0.
   - **I want to see my friend's streak** -> shows the other user's streak.

Extra command: `/id` replies with your chat id (used once to fill `HI_CHAT_ID` and `TORNILLO_CHAT_ID`).

---

## Deployment (Render)

The bot switches modes automatically: **webhooks** on Render (Telegram pushes updates to the service), **polling** on a local machine. It detects Render through the `RENDER_EXTERNAL_URL` environment variable that Render sets by itself.

Create a **Web Service** on [render.com](https://render.com) pointing to this repository with:

| Setting               | Value                                                          |
| --------------------- | -------------------------------------------------------------- |
| Build Command         | `pip install -r requirements.txt`                              |
| Start Command         | `python src/main.py`                                           |
| Environment Variables | `TOKEN_BOT`, `HI_CHAT_ID`, `TORNILLO_CHAT_ID` (same as `.env`) |

Note for the free plan: the instance spins down after ~15 minutes without traffic, so the first message after a quiet period takes ~30-60 seconds to be answered while the service wakes up. Telegram retries the delivery, so no message is lost.

---

## Project Structure

```
src/
|-- main.py                      # Entry point: builds the app and wires the ConversationHandler
|-- Controllers/
|   |-- tracker_controller.py    # Conversation flow: questions, buttons and replies
|-- Models/
    |-- streak_model.py          # Streak logic, stored in the chat's pinned message
```

---

## How It Works

The bot uses a `ConversationHandler` with two states:

- `WHO_ARE_YOU` - waiting for the answer to the first question.
- `MENU` - waiting for the user to pick a menu option.

There is no database. Telegram bots cannot read the chat history, but they can read the chat's **pinned message**, so the bot stores each user's streak in a pinned status message like `Streak: 5 (last report: 2026-07-13)` and reads it back with `get_chat`. The data lives inside Telegram itself, so it survives restarts and redeploys - perfect for hosts with an ephemeral filesystem like Render's free plan. When a day is reported:

- Last report was **today** -> already reported, nothing changes.
- Last report was **yesterday** -> streak + 1.
- Anything **older** (or a new user) -> streak restarts at 1.

Each private chat has its own pinned message, so each user has their own independent streak.

The friend's streak works the same way: a private chat id equals the user's Telegram id, and the bot can read the pinned message of any chat it knows. With `HI_CHAT_ID` and `TORNILLO_CHAT_ID` configured, the bot reads the *other* user's pinned message to answer "I want to see my friend's streak".

---

## Configuration

| Variable              | Where           | Description                                          |
| --------------------- | --------------- | ---------------------------------------------------- |
| `TOKEN_BOT`           | `.env` / Render | Bot token given by `@BotFather`                      |
| `HI_CHAT_ID`          | `.env` / Render | Private chat id of El Hi (get it with `/id`)         |
| `TORNILLO_CHAT_ID`    | `.env` / Render | Private chat id of El tornillo (get it with `/id`)   |
| `RENDER_EXTERNAL_URL` | Render (auto)   | Public URL of the service; enables webhook mode      |
| `PORT`                | Render (auto)   | Port the webhook server listens on (default `8443`)  |

---

## Notes

- Do not unpin or delete the bot's pinned status message - it IS the storage. If it disappears, the streak starts over.
- Handlers must be registered **before** `run_polling()` - anything after it never runs.

---

## License

MIT License
