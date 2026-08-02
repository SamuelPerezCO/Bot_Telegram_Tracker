"""Registers (or removes) the Telegram webhook that points to Vercel.

Telegram needs to be told once where to push the updates. Run this after
the first deploy, and again only if the URL or the secret changes.

    python scripts/set_webhook.py https://<project>.vercel.app
    python scripts/set_webhook.py delete     # back to local polling
    python scripts/set_webhook.py info       # what Telegram has right now

TOKEN_BOT is read from .env, and WEBHOOK_SECRET too if it is set (the
same value must exist in the Vercel environment variables).
"""

from dotenv import load_dotenv
from urllib.parse import urlencode
from urllib.request import urlopen
import json
import os
import sys


API = "https://api.telegram.org/bot{token}/{method}?{params}"


def call(token , method , **params):
    """Calls a method of the Telegram Bot API.

    Args:
        token (str): Bot token.
        method (str): Name of the API method.
        **params: Query parameters of the method.

    Returns:
        dict: The decoded JSON answer from Telegram.
    """
    url = API.format(token=token , method=method , params=urlencode(params))
    with urlopen(url) as answer:
        return json.load(answer)


def main():
    """Reads the command line argument and talks to Telegram."""
    load_dotenv()
    token = os.getenv("TOKEN_BOT")
    secret = os.getenv("WEBHOOK_SECRET")

    if not token:
        sys.exit("TOKEN_BOT is not set (add it to .env)")
    if len(sys.argv) != 2:
        sys.exit(__doc__)

    argument = sys.argv[1]

    if argument == "delete":
        print(call(token , "deleteWebhook" , drop_pending_updates="true"))
        return

    if argument == "info":
        print(json.dumps(call(token , "getWebhookInfo") , indent=2))
        return

    url = f"{argument.rstrip('/')}/api/webhook"
    params = {"url": url , "allowed_updates": json.dumps(["message"])}
    if secret:
        params["secret_token"] = secret
    else:
        print("Warning: WEBHOOK_SECRET is not set, the webhook URL will accept updates from anyone")

    print(f"Setting webhook to {url}")
    print(call(token , "setWebhook" , **params))


if __name__ == "__main__":
    main()
