# Bot_Telegram_Tracker

A Telegram bot that tracks a daily streak for each of your personal goals. Write your goals and the period you give yourself, then report every day, goal by goal - miss one and only that one restarts.

Bot: [t.me/Tracker90Bot](https://t.me/Tracker90Bot)

---

## Features

- Write your own goals: the bot asks how many, then asks for them one by one
- Choose the period you give yourself to complete them (`90 days`, `2 weeks`, `3 months`)
- Daily report goal by goal: one question per goal, Yes or No
- Every goal is its own streak, shown as `12/90`: a No sends only that goal back to 0
- Answering only counts once per day, and an interrupted report continues where it stopped
- Check your friend's goals from your own chat
- A daily reminder at the hour you choose, listing the goals still pending
- No database: everything is stored in the chat's pinned message
- Your goals and their counters are always visible at the top of the chat

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
2. Answer the "Who are you?" question - the bot shows your goals and the menu.
3. Choose an option:
   - **I want to add my goals** -> the bot asks how many goals you want, then asks for each one, and finally for the period you give yourself to complete them.
   - **I want to report my day** -> the bot asks about every goal, one message each: answer **Yes** to add a day to that goal, **No** to send it back to 0.
   - **I want to see my goals** -> shows your goals with their counters.
   - **I want to see my friend's goals** -> shows the other user's goals.

While the bot is asking for your goals, writing `cancel` stops the questions and keeps what you already answered.

A report looks like this:

```
1. Wake Up at 5:00 am 12/90
2. Journal 12/90
3. No FAP 0/90
4. No Porn 12/90
5. Diary Commit 12/90
```

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

### Daily reminder

The bot cannot wake itself up: between two messages there is no process running. An external scheduler calls `/api/remind`, and that function sends "Ready to report your day?" to whoever still has goals pending, listing them. Anybody who already reported everything is skipped, so it never nags for nothing.

1. Add `CRON_SECRET` (any random string) to the Vercel environment variables and redeploy. Until it exists the endpoint answers `500` and sends nothing, so the reminder is never accidentally open to the internet.
2. Create a free job on [cron-job.org](https://cron-job.org):

   | Field    | Value                                              |
   | -------- | -------------------------------------------------- |
   | URL      | `https://your-project.vercel.app/api/remind`       |
   | Schedule | Every day at `18:00`                               |
   | Timezone | `America/Bogota`                                   |
   | Header   | `X-Cron-Secret: your_cron_secret`                  |

   The secret can also go in the URL as `?key=your_cron_secret` if adding a header is not convenient.

3. Use **Test run** in cron-job.org to check it: the response body says what happened with each user, for example `El Hi: reminded, 2 goal(s) pending` / `El tornillo: skipped, already reported today`.

Any other scheduler works the same way, since it is only an HTTP call. Vercel's own cron jobs can call it too (`"crons": [{"path": "/api/remind", "schedule": "0 23 * * *"}]` in `vercel.json`, UTC), but on the Hobby plan they fire anywhere inside the scheduled hour, which is why the external scheduler is used here.

**Going back to polling on your machine:** Telegram refuses to do both at the same time, so remove the webhook first with `python scripts/set_webhook.py delete`, and set it again when you are done.

Notes on the free plan: functions are billed per invocation and stay well inside the free tier for a two-user bot. A cold start makes the first message after a quiet period take a couple of seconds - much better than the ~30-60s Render's free plan needed to wake up a spun-down instance.

---

## Project Structure

```
api/
|-- index.py                     # Vercel entry point: one HTTP request = one update
|                                # (the name is constrained by Vercel, see the file)
|-- remind.py                    # Called by the scheduler once a day: sends the reminder
scripts/
|-- set_webhook.py               # Registers/removes the webhook in Telegram
src/
|-- bot.py                       # Builds the application and routes every message
|-- run_local.py                 # Local entry point: runs the bot with polling
|                                # (must not be named main.py, see the file)
|-- Controllers/
|   |-- tracker_controller.py    # Conversation flow: questions, buttons and replies
|-- Models/
    |-- streak_model.py          # Goals and their streaks, stored in the pinned message
vercel.json                      # Function config (bundles src/ with the function)
```

---

## How It Works

The bot keeps **no state in memory**. On a serverless host every update may be served by a different instance, so a `ConversationHandler` (which remembers the step each user is in) would forget the conversation between two messages. Instead, each step shows buttons with different texts and every message is routed by its own text:

- `El Hi` / `El tornillo` - answer to the first question, shows the goals and the menu.
- `I want to ...` - one of the four menu options.
- Anything else - either the answer to a question the bot asked (a goal, a period, a Yes/No), or a reminder to press a button.

There is no database either. Telegram bots cannot read the chat history, but they can read the chat's **pinned message**, so the bot stores everything in a pinned status message and reads it back with `get_chat`. The data lives inside Telegram itself, so it survives restarts and redeploys - which is exactly what a serverless host needs, since it has no disk of its own:

```
🎯 Goals (5, period: 90 days)
1. Wake Up at 5:00 am 12/90 (last: 2026-08-09)
2. Journal 12/90 (last: 2026-08-09)
3. No FAP 0/90 (last: 2026-08-09)
```

The questions that need a free text answer (how many goals, each goal, the period, and the Yes/No of every goal) also need to remember what was asked, so the same pinned message carries it: the header ends with `[waiting: goal]` or `[waiting: report]` while a question is open, and nothing when the user is back in the menu. That is what lets the questionnaire survive being served by five different serverless instances.

Each goal is its own streak, with its own last answer. When a goal is reported:

- Answered **yes** and it was also achieved **yesterday** -> counter + 1.
- Answered **yes** after a break (or for the first time) -> counter restarts at 1.
- Answered **no** -> counter back to 0. The other goals are not touched.
- Already answered **today** -> the bot does not ask about it again.

The last rule is also what makes an interrupted report resume by itself: the next question is simply the first goal that has no answer for today.

Each private chat has its own pinned message, so each user has their own independent goals. The friend's goals work the same way: a private chat id equals the user's Telegram id, and the bot can read the pinned message of any chat it knows. With `HI_CHAT_ID` and `TORNILLO_CHAT_ID` configured, the bot reads the *other* user's pinned message to answer "I want to see my friend's goals".

---

## Configuration

| Variable           | Where           | Description                                                             |
| ------------------ | --------------- | ----------------------------------------------------------------------- |
| `TOKEN_BOT`        | `.env` / Vercel | Bot token given by `@BotFather`                                         |
| `HI_CHAT_ID`       | `.env` / Vercel | Private chat id of El Hi (get it with `/id`)                            |
| `TORNILLO_CHAT_ID` | `.env` / Vercel | Private chat id of El tornillo (get it with `/id`)                      |
| `WEBHOOK_SECRET`   | `.env` / Vercel | Random string; Telegram sends it back so nobody can fake updates        |
| `CRON_SECRET`      | Vercel          | Random string the scheduler sends to `/api/remind`; without it the reminder is disabled |
| `TIMEZONE`         | `.env` / Vercel | Timezone used to decide what "today" is (default `America/Bogota`)      |

---

## Notes

- Do not unpin or delete the bot's pinned status message - it IS the storage. If it disappears, the goals and their counters are gone.
- Handlers must be registered **before** `run_polling()` - anything after it never runs.
- Polling and the webhook are mutually exclusive in Telegram. If the bot ignores you locally, the webhook is probably still set: `python scripts/set_webhook.py delete`.
- The webhook always answers `200`, even when an update fails. A different code makes Telegram redeliver the same update for hours; the real error is in the Vercel function logs.

---

## License

MIT License
