"""Vercel entry point: one HTTP request = one Telegram update.

Vercel is serverless, so there is no process running between messages:
Telegram POSTs an update to the deployment, this function builds the
bot, processes that single update and dies.

Register the webhook once with:

    python scripts/set_webhook.py https://<project>.vercel.app

Two naming rules, both learned the hard way:

- The file must live in a location Vercel accepts as an entrypoint
  (api/index.py is one). Anything else fails the build with
  "No python entrypoint found in default locations".
- It must NOT be called telegram.py: Vercel puts the directory of the
  function on sys.path, so that name would shadow python-telegram-bot
  and `from telegram import ...` would import this file instead.
"""

from http.server import BaseHTTPRequestHandler
import asyncio
import json
import os
import sys
import traceback

# The bot modules live in src/, which is not on the path inside Vercel.
# The layout of the bundle is not identical to the repository, so every
# plausible location is tried instead of assuming one.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
for _candidate in (
    os.path.join(BASE_DIR , ".." , "src") ,
    os.path.join(os.getcwd() , "src") ,
    os.path.join("/var/task" , "src") ,
):
    _candidate = os.path.normpath(_candidate)
    if os.path.isdir(_candidate) and _candidate not in sys.path:
        sys.path.insert(0 , _candidate)

# An exception while importing kills the whole function and Vercel can
# only answer a generic 500, so the failure is captured and reported by
# the health check instead.
IMPORT_ERROR = None
try:
    from telegram import Update
    from bot import build_application
    from Controllers import tracker_controller
except Exception:
    IMPORT_ERROR = traceback.format_exc()
    print(IMPORT_ERROR , file=sys.stderr)


# Shared secret Telegram sends back in every request, so nobody else can
# post fake updates to the public URL. Set by scripts/set_webhook.py.
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")


async def _process(payload):
    """Feeds one update to the bot.

    The application is created, started and shut down inside the request:
    a serverless instance may be frozen or destroyed right after the
    response, so nothing can be kept alive between updates.

    Args:
        payload (dict): The update as sent by Telegram.
    """
    application = build_application()
    await application.initialize()
    try:
        await application.process_update(Update.de_json(payload , application.bot))
    finally:
        await application.shutdown()


class handler(BaseHTTPRequestHandler):
    """HTTP entry point expected by the Vercel Python runtime."""

    def do_POST(self):
        """Handles an update pushed by Telegram."""
        if IMPORT_ERROR:
            self._reply(200 , "ok")  # nothing can be done with this update
            return
        if WEBHOOK_SECRET and self.headers.get("X-Telegram-Bot-Api-Secret-Token") != WEBHOOK_SECRET:
            self._reply(401 , "unauthorized")
            return

        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b"{}"

        try:
            asyncio.run(_process(json.loads(body)))
        except Exception as error:
            # Answering 200 anyway: a non-2xx makes Telegram redeliver the
            # same update for hours. The error is in the Vercel logs.
            print(f"Error processing update: {error!r}" , file=sys.stderr)

        self._reply(200 , "ok")

    def do_GET(self):
        """Health check: says what is wrong when the bot cannot load."""
        if IMPORT_ERROR:
            report = [
                "The bot modules could not be imported." ,
                "" ,
                f"__file__   : {os.path.abspath(__file__)}" ,
                f"cwd        : {os.getcwd()}" ,
                f"cwd files  : {sorted(os.listdir(os.getcwd()))}" ,
                f"base files : {sorted(os.listdir(BASE_DIR))}" ,
                f"sys.path   : {sys.path}" ,
                "" ,
                IMPORT_ERROR ,
            ]
            self._reply(500 , "\n".join(report))
            return

        if not os.getenv("TOKEN_BOT"):
            self._reply(500 , "Missing environment variable: TOKEN_BOT")
            return

        # The people are configured in USERS, with the two old
        # variables still accepted; the controller knows both forms.
        users = tracker_controller.configured_users()
        if not users:
            self._reply(500 , "No users configured: set USERS to \"name:chat_id\" pairs separated by commas")
            return

        # Only whether it exists, never the value: a secret that does not
        # match the one used to register the webhook rejects every update.
        secret_state = "set" if WEBHOOK_SECRET else "not set (updates are not verified)"
        people = " , ".join(name for _ , name in users)
        self._reply(200 , f"Tracker bot webhook is alive\nwebhook secret: {secret_state}\nusers: {people}")

    def _reply(self , status , text):
        """Writes a plain text response.

        Args:
            status (int): HTTP status code.
            text (str): Body of the response.
        """
        body = text.encode()
        self.send_response(status)
        self.send_header("Content-Type" , "text/plain; charset=utf-8")
        self.send_header("Content-Length" , str(len(body)))
        self.end_headers()
        self.wfile.write(body)
