# Bot_Telegram_Tracker

A Telegram bot that tracks a daily streak for each of your personal goals. Write your goals and the period you give yourself, then report every day, goal by goal - miss one and only that one restarts.

Bot: [t.me/Tracker90Bot](https://t.me/Tracker90Bot)

---

## Features

- Write your own goals: the bot asks how many, then asks for them one by one
- An hour per goal: the bot reminds you about `Wake up at 5:00` at 05:00 and about `Journal` at 22:00
- Choose the period you give yourself to complete them (`90 days`, `2 weeks`, `3 months`)
- Daily report goal by goal: one question per goal, **Yes**, **No** or **Not yet**
- "Not yet" changes nothing and asks again later, so you can confirm the morning goals in the morning
- Every goal is its own streak, shown as `12/90`: a No sends only that goal back to 0
- Answering only counts once per day, and an interrupted report continues where it stopped
- Any number of people: check everybody else's goals from your own chat, and they see when you report
- Two phones, one person: a second chat shares the same goals and receives the same reminders
- A daily summary of what is still pending, at the hour you choose
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
3. Create a `.env` file in the project root with your bot token and the people using the bot:
   ```
   TOKEN_BOT=your_token_from_botfather
   USERS=El Hi:11111111,El tornillo:22222222,Samuel:33333333
   WEBHOOK_SECRET=any_random_string
   ```
   `USERS` is a list of `name:chat_id` separated by commas. **Adding a person is adding a pair there** - the names become the buttons of the "Who are you?" question, and everybody sees everybody else's goals. To get a chat id, ask the person to send `/id` to the bot: it replies with the number. This only needs to be done once per person.

   The older `HI_CHAT_ID` / `TORNILLO_CHAT_ID` variables still work when `USERS` is not set, so an existing deployment keeps running until it is migrated.

4. If somebody uses the bot from **two phones** (two Telegram accounts, so two chats for Telegram), add the second chat with the same name:
   ```
   SEND_REMINDER=El Hi:33333333
   ```
   That chat becomes the same person: it shares the goals of the chat in `USERS`, can report from either side, and both chats receive every reminder and every notification. The goals themselves stay in **one** pinned message, the one of the chat listed in `USERS` - which is the chat where the status messages keep appearing.

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
   - **I want to add my goals** -> the bot asks how many goals you want, then for each one asks the goal and **at what time you want its reminder**, and finally the period you give yourself to complete them.
   - **I want to report my day** -> the bot asks about every goal, one message each: answer **Yes** to add a day to that goal, **No** to send it back to 0, **Not yet** when the day is not over and you do not know yet.
   - **I want to see my goals** -> shows your goals with their counters.
   - **I want to see my friends' goals** -> shows everybody else's goals.

Adding a goal goes like this:

```
BOT : Tell me goal number 1
YOU : Wake up at 5:00
BOT : At what time do you want a reminder for "Wake up at 5:00"?
      For example: 5:00, 17:30, 9 pm
      Answer "no" if you do not want one.
YOU : 5:00
```

The hour accepts `5`, `5:00`, `05:00`, `5 am`, `9 pm`, `17:30`. Answering `no` (or `skip`) leaves that goal without a reminder. Writing `cancel` at any moment stops the questions and keeps what you already answered.

A report looks like this:

```
1. Wake Up at 5:00 am 12/90 ⏰05:00
2. Journal 12/90 ⏰22:00
3. No FAP 0/90
4. No Porn 12/90
5. Diary Commit 12/90
```

Extra command: `/id` replies with your chat id (used once per person to fill `USERS`).

---

## Deployment (Vercel)

In production the bot is a **serverless function** on Vercel: there is no process running between messages. Telegram POSTs each update to the deployment, the function builds the bot, answers that single update and dies. Locally the bot still runs with **polling** (`src/run_local.py`), which is more comfortable to develop with.

1. Push the repository to GitHub and import it on [vercel.com](https://vercel.com) (**Add New -> Project**). No build settings are needed: `vercel.json` already describes the function and `requirements.txt` is installed automatically.
2. In **Settings -> Environment Variables** add `TOKEN_BOT`, `USERS`, `WEBHOOK_SECRET` (any random string you invent, it just has to match the one in your `.env`) and `CRON_SECRET`.
3. Deploy, then tell Telegram where to push the updates - once, from your machine:

   ```bash
   python scripts/set_webhook.py https://your-project.vercel.app
   ```

   Check it whenever you are in doubt with `python scripts/set_webhook.py info`.

Open `https://your-project.vercel.app/api/index` in a browser to confirm the deployment is alive; it answers with a short text. `set_webhook.py` probes that URL by itself and refuses to change anything if the deployment is not answering, so a broken deploy cannot take the bot down.

### Reminders

The bot cannot wake itself up: between two messages there is no process running. An external scheduler calls `/api/remind` **every minute**, and that single call decides what is due:

- the reminder of every goal whose hour has just arrived, for every user;
- once a day at `DAILY_REMINDER` (18:00 by default), the summary of what is still pending.

The hours live inside each goal, so the schedule never has to change when somebody adds a goal at a new hour - only this endpoint has to run often enough to notice.

1. Add `CRON_SECRET` (any random string) to the Vercel environment variables and redeploy. Until it exists the endpoint answers `500` and sends nothing, so the reminders are never accidentally open to the internet.
2. Create a free job on [cron-job.org](https://cron-job.org):

   | Field    | Value                                              |
   | -------- | -------------------------------------------------- |
   | URL      | `https://your-project.vercel.app/api/remind`       |
   | Schedule | Every minute (`* * * * *`)                         |
   | Header   | `X-Cron-Secret: your_cron_secret`                  |

   The secret can also go in the URL as `?key=your_cron_secret` if adding a header is not convenient. The timezone of the job does not matter here: the bot compares the hours in `TIMEZONE`, so a job running every minute is right whatever the scheduler thinks the time is. The free plan allows one-minute intervals and any number of jobs.

3. Use **Test run** in cron-job.org to check it. The response body says what happened: `nothing due` most of the time, and lines like `El Hi: reminded about goal(s) 1` or `El tornillo: skipped, already reported today` when there was something to do.

A missed run is not a lost reminder: a goal reminder is still sent up to 60 minutes late (`CATCH_UP_MINUTES`), and never twice, because the day it was sent is written next to the goal. Vercel's own cron jobs cannot replace this on the Hobby plan - there they are limited to one run per day.

**Going back to polling on your machine:** Telegram refuses to do both at the same time, so remove the webhook first with `python scripts/set_webhook.py delete`, and set it again when you are done.

Notes on the free plan: functions are billed per invocation. The reminder endpoint running every minute adds ~44k invocations a month, which still fits the free tier for a handful of users; each run does nothing but read the pinned message of each user and answer `nothing due`. A cold start makes the first message after a quiet period take a couple of seconds - much better than the ~30-60s Render's free plan needed to wake up a spun-down instance.

---

## Project Structure

```
api/
|-- index.py                     # Vercel entry point: one HTTP request = one update
|                                # (the name is constrained by Vercel, see the file)
|-- remind.py                    # Called by the scheduler every minute: sends what is due
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

- The name of a user (`El Hi`, `El tornillo`, ...) - answer to the first question, shows the goals and the menu. The pattern is built from `USERS` when the application starts, so a new person needs no code change.
- `I want to ...` - one of the four menu options.
- Anything else - either the answer to a question the bot asked (a goal, an hour, a period, a Yes/No), or a reminder to press a button.

There is no database either. Telegram bots cannot read the chat history, but they can read the chat's **pinned message**, so the bot stores everything in a pinned status message and reads it back with `get_chat`. The data lives inside Telegram itself, so it survives restarts and redeploys - which is exactly what a serverless host needs, since it has no disk of its own:

```
🎯 Goals (5, period: 90 days)
1. Wake Up at 5:00 am 12/90 (last: 2026-08-09, at: 05:00, sent: 2026-08-09)
2. Journal 12/90 (last: 2026-08-09, at: 22:00, sent: none)
3. No FAP 0/90 (last: 2026-08-09, at: none, sent: none)
```

Every goal carries its counter, the day it was last answered, the hour of its reminder and the day that reminder was last sent - which is what makes the reminder arrive once a day and only once.

The questions that need a free text answer (how many goals, each goal, its hour, the period, and the Yes/No of every goal) also need to remember what was asked, so the same pinned message carries it: the header ends with `[waiting: goal]`, `[waiting: time]` or `[waiting: report]` while a question is open, and nothing when the user is back in the menu. That is what lets the questionnaire survive being served by five different serverless instances.

Each goal is its own streak, with its own last answer. When a goal is reported:

- Answered **yes** and it was also achieved **yesterday** -> counter + 1.
- Answered **yes** after a break (or for the first time) -> counter restarts at 1.
- Answered **no** -> counter back to 0. The other goals are not touched.
- Answered **not yet** -> nothing changes at all. The goal is only put aside for the rest of this report, and comes back the next time you report.
- Already answered **today** -> the bot does not ask about it again.

The last rule is also what makes an interrupted report resume by itself: the next question is simply the first goal that has no answer for today.

"Not yet" is what makes a report at 06:00 useful: confirm `Wake up at 5:00`, leave the rest for later, and report again in the evening - only the goals still without an answer are asked. The numbers put aside are the `[later: 2,3]` of the header, and they are forgotten as soon as a new report starts. A goal left for later still gets its own reminder at its hour, and still appears in the daily summary as pending.

Each private chat has its own pinned message, so each person has their own independent goals. When somebody uses two chats (`SEND_REMINDER`), only the chat listed in `USERS` holds the pinned message: every update coming from the second chat is answered where it was written, but read and written against that one status. That is the whole trick - one source of truth, two doors into it.

The friends' goals work the same way: a private chat id equals the user's Telegram id, and the bot can read the pinned message of any chat it knows. To answer "I want to see my friends' goals" the bot simply reads the pinned message of every *other* chat id in `USERS` - which is why adding a third (or tenth) person is a configuration change and nothing else.

---

## Configuration

| Variable           | Where           | Description                                                             |
| ------------------ | --------------- | ----------------------------------------------------------------------- |
| `TOKEN_BOT`        | `.env` / Vercel | Bot token given by `@BotFather`                                         |
| `USERS`            | `.env` / Vercel | The people using the bot, as `name:chat_id` separated by commas (get each id with `/id`) |
| `SEND_REMINDER`    | `.env` / Vercel | Extra chats of somebody already in `USERS`, same `name:chat_id` shape; they share that person's goals and get the reminders |
| `WEBHOOK_SECRET`   | `.env` / Vercel | Random string; Telegram sends it back so nobody can fake updates        |
| `CRON_SECRET`      | Vercel          | Random string the scheduler sends to `/api/remind`; without it the reminders are disabled |
| `DAILY_REMINDER`   | `.env` / Vercel | Hour of the "what is still pending" summary (default `18:00`, `off` to disable) |
| `TIMEZONE`         | `.env` / Vercel | Timezone used for "today" and for every reminder hour (default `America/Bogota`) |
| `HI_CHAT_ID`       | `.env` / Vercel | Old two-user configuration, only used when `USERS` is not set           |
| `TORNILLO_CHAT_ID` | `.env` / Vercel | Old two-user configuration, only used when `USERS` is not set           |

---

## Notes

- Do not unpin or delete the bot's pinned status message - it IS the storage. If it disappears, the goals and their counters are gone.
- Handlers must be registered **before** `run_polling()` - anything after it never runs.
- Polling and the webhook are mutually exclusive in Telegram. If the bot ignores you locally, the webhook is probably still set: `python scripts/set_webhook.py delete`.
- The webhook always answers `200`, even when an update fails. A different code makes Telegram redeliver the same update for hours; the real error is in the Vercel function logs.

---

## License

MIT License
