"""Vercel entry point: one HTTP request = one Telegram update.

Vercel is serverless, so there is no process running between messages:
Telegram POSTs an update to https://<project>.vercel.app/api/telegram,
this function builds the bot, processes that single update and dies.

Register the webhook once with:

    python scripts/set_webhook.py https://<project>.vercel.app
"""

from http.server import BaseHTTPRequestHandler
import asyncio
import json
import os
import sys

# The bot modules live in src/, which is not on the path inside Vercel.
sys.path.insert(0 , os.path.join(os.path.dirname(os.path.abspath(__file__)) , ".." , "src"))

from telegram import Update

from bot import build_application


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
        """Health check, handy to see the deployment is alive."""
        self._reply(200 , "Tracker bot webhook is alive")

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
