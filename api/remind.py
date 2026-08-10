"""Vercel entry point for the reminders.

Nothing runs between two updates on a serverless host, so the bot
cannot wake itself up. An external scheduler (cron-job.org) calls this
URL every minute and the function decides what is due:

    https://<project>.vercel.app/api/remind?key=<CRON_SECRET>

- The reminder of every goal whose hour has just arrived. Each user
  chooses that hour when writing the goal, so the times are data and
  not configuration: only this endpoint has to run often enough.
- The summary of what is still pending, once a day at DAILY_REMINDER
  (18:00 by default, "off" to disable it).

The key can also travel as an X-Cron-Secret header. Without it the
request is rejected, otherwise anybody could make the bot write to
every user as many times as they wanted.

See api/index.py for the two naming rules this file also follows.
"""

from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse , parse_qs
import asyncio
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
# only answer a generic 500, so the failure is captured and reported in
# the response instead.
IMPORT_ERROR = None
try:
    from bot import build_application
    from Controllers.tracker_controller import send_due_reminders , send_daily_reminders
    from Models import streak_model
except Exception:
    IMPORT_ERROR = traceback.format_exc()
    print(IMPORT_ERROR , file=sys.stderr)


# Shared secret the scheduler has to send, so the reminders cannot be
# triggered by anybody who finds the URL.
CRON_SECRET = os.getenv("CRON_SECRET")


async def _remind():
    """Builds the bot and sends whatever is due right now.

    The application is created, started and shut down inside the
    request, exactly like in api/index.py: a serverless instance may be
    frozen or destroyed right after the response.

    Returns:
        list[str]: What was done, for the scheduler log.
    """
    application = build_application()
    await application.initialize()
    try:
        report = await send_due_reminders(application.bot)

        # The summary has no "already sent" mark of its own, so it goes
        # out on the exact minute instead of within a catch-up window:
        # missing a summary matters much less than sending it twice.
        daily = os.getenv("DAILY_REMINDER" , "18:00").strip()
        if daily.lower() not in ("" , "off") and daily == streak_model.now_hhmm():
            report += await send_daily_reminders(application.bot)

        return report
    finally:
        await application.shutdown()


class handler(BaseHTTPRequestHandler):
    """HTTP entry point expected by the Vercel Python runtime."""

    def do_GET(self):
        """Sends what is due. Called by the scheduler every minute."""
        if IMPORT_ERROR:
            self._reply(500 , f"The bot modules could not be imported.\n\n{IMPORT_ERROR}")
            return
        if not CRON_SECRET:
            self._reply(500 , "CRON_SECRET is not set, so the reminder is disabled")
            return

        given = self.headers.get("X-Cron-Secret") or parse_qs(urlparse(self.path).query).get("key" , [None])[0]
        if given != CRON_SECRET:
            self._reply(401 , "unauthorized")
            return

        try:
            report = asyncio.run(_remind())
        except Exception as error:
            # A 500 here is wanted: the scheduler shows it as a failed
            # run, which is how a broken reminder gets noticed.
            print(f"Error sending the reminders: {error!r}" , file=sys.stderr)
            self._reply(500 , f"Error sending the reminders: {error!r}")
            return

        # Most of the 1440 runs of a day have nothing to do, and saying
        # so keeps the scheduler log readable.
        self._reply(200 , "\n".join(report) or "nothing due")

    # cron-job.org can be configured to POST instead of GET, so both do
    # the same thing.
    do_POST = do_GET

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
