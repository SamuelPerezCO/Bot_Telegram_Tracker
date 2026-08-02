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

- Python 3.12+ (the version the Vercel Python runtime uses)
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- A free [Vercel](https://vercel.com) account to host the bot

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
   HI_CHAT_ID=chat_id_of_el_hi
   TORNILLO_CHAT_ID=chat_id_of_el_tornillo
   WEBHOOK_SECRET=any_random_string
   ```
   To get a chat id, send `/id` to the bot - it replies with the number. This only needs to be done once per user.

   `WEBHOOK_SECRET` is only needed to deploy: it is sent to Telegram when registering the webhook and returned in every update, so the public URL rejects anything that does not come from Telegram. The same value goes in the Vercel environment variables.

---

## Usage

Run the bot:

```bash
cd src
python run_local.py
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

## Deployment (Vercel)

In production the bot is a **serverless function** on Vercel: there is no process running between messages. Telegram POSTs each update to the deployment, the function builds the bot, answers that single update and dies. Locally the bot still runs with **polling** (`src/run_local.py`), which is more comfortable to develop with.

1. Push the repository to GitHub and import it on [vercel.com](https://vercel.com) (**Add New -> Project**). No build settings are needed: `vercel.json` already describes the function and `requirements.txt` is installed automatically.
2. In **Settings -> Environment Variables** add `TOKEN_BOT`, `HI_CHAT_ID`, `TORNILLO_CHAT_ID` and `WEBHOOK_SECRET` (any random string you invent, it just has to match the one in your `.env`).
3. Deploy, then tell Telegram where to push the updates - once, from your machine:

   ```bash
   python scripts/set_webhook.py https://your-project.vercel.app
   ```

   Check it whenever you are in doubt with `python scripts/set_webhook.py info`.

Open `https://your-project.vercel.app/api/index` in a browser to confirm the deployment is alive; it answers with a short text. `set_webhook.py` probes that URL by itself and refuses to change anything if the deployment is not answering, so a broken deploy cannot take the bot down.

**Going back to polling on your machine:** Telegram refuses to do both at the same time, so remove the webhook first with `python scripts/set_webhook.py delete`, and set it again when you are done.

Notes on the free plan: functions are billed per invocation and stay well inside the free tier for a two-user bot. A cold start makes the first message after a quiet period take a couple of seconds - much better than the ~30-60s Render's free plan needed to wake up a spun-down instance.

---

## Project Structure

```
api/
|-- index.py                     # Vercel entry point: one HTTP request = one update
|                                # (the name is constrained by Vercel, see the file)
scripts/
|-- set_webhook.py               # Registers/removes the webhook in Telegram
src/
|-- bot.py                       # Builds the application and routes every message
|-- run_local.py                 # Local entry point: runs the bot with polling
|                                # (must not be named main.py, see the file)
|-- Controllers/
|   |-- tracker_controller.py    # Conversation flow: questions, buttons and replies
|-- Models/
    |-- streak_model.py          # Streak logic, stored in the chat's pinned message
vercel.json                      # Function config (bundles src/ with the function)
```

---

## How It Works

The bot keeps **no state in memory**. On a serverless host every update may be served by a different instance, so a `ConversationHandler` (which remembers the step each user is in) would forget the conversation between two messages. Instead, each step shows buttons with different texts and every message is routed by its own text:

- `El Hi` / `El tornillo` - answer to the first question, shows the streak and the menu.
- `I want to ...` - one of the three menu options.
- Anything else - the bot asks the user to press a button or send `/start`.

There is no database either. Telegram bots cannot read the chat history, but they can read the chat's **pinned message**, so the bot stores each user's streak in a pinned status message like `Streak: 5 (last report: 2026-07-13)` and reads it back with `get_chat`. The data lives inside Telegram itself, so it survives restarts and redeploys - which is exactly what a serverless host needs, since it has no disk of its own. When a day is reported:

- Last report was **today** -> already reported, nothing changes.
- Last report was **yesterday** -> streak + 1.
- Anything **older** (or a new user) -> streak restarts at 1.

Each private chat has its own pinned message, so each user has their own independent streak.

The friend's streak works the same way: a private chat id equals the user's Telegram id, and the bot can read the pinned message of any chat it knows. With `HI_CHAT_ID` and `TORNILLO_CHAT_ID` configured, the bot reads the *other* user's pinned message to answer "I want to see my friend's streak".

---

## Configuration

| Variable           | Where           | Description                                                             |
| ------------------ | --------------- | ----------------------------------------------------------------------- |
| `TOKEN_BOT`        | `.env` / Vercel | Bot token given by `@BotFather`                                         |
| `HI_CHAT_ID`       | `.env` / Vercel | Private chat id of El Hi (get it with `/id`)                            |
| `TORNILLO_CHAT_ID` | `.env` / Vercel | Private chat id of El tornillo (get it with `/id`)                      |
| `WEBHOOK_SECRET`   | `.env` / Vercel | Random string; Telegram sends it back so nobody can fake updates        |
| `TIMEZONE`         | `.env` / Vercel | Timezone used to decide what "today" is (default `America/Bogota`)      |

---

## Notes

- Do not unpin or delete the bot's pinned status message - it IS the storage. If it disappears, the streak starts over.
- Handlers must be registered **before** `run_polling()` - anything after it never runs.
- Polling and the webhook are mutually exclusive in Telegram. If the bot ignores you locally, the webhook is probably still set: `python scripts/set_webhook.py delete`.
- The webhook always answers `200`, even when an update fails. A different code makes Telegram redeliver the same update for hours; the real error is in the Vercel function logs.

---

## License

MIT License
