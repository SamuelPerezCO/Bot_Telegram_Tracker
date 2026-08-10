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
from urllib.error import HTTPError , URLError
from urllib.parse import urlencode
from urllib.request import urlopen
import json
import os
import sys


API = "https://api.telegram.org/bot{token}/{method}?{params}"

# Where the function may answer, depending on how Vercel decides to route
# the project. The first one that replies to the health check is used, so
# a change in Vercel's routing does not silently break the webhook.
CANDIDATE_PATHS = ("/api/index" , "/api" , "/")


def find_endpoint(base):
    """Finds which URL of the deployment the bot is answering on.

    Args:
        base (str): Root URL of the deployment, without trailing slash.

    Returns:
        str | None: The working URL, or None if none of them answered.
    """
    for path in CANDIDATE_PATHS:
        url = base + path
        try:
            with urlopen(url , timeout=30) as answer:
                body = answer.read().decode(errors="replace")
                if answer.status == 200 and "alive" in body:
                    print(f"  {url} -> alive")
                    return url
                print(f"  {url} -> {answer.status}: {body[:400]}")
        except HTTPError as error:
            print(f"  {url} -> {error.code}: {error.read().decode(errors='replace')[:400]}")
        except URLError as error:
            print(f"  {url} -> unreachable ({error.reason})")
    return None


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

    print("Looking for the deployment endpoint...")
    url = find_endpoint(argument.rstrip("/"))
    if url is None:
        sys.exit(
            "\nNone of the URLs answered the health check, so the webhook was NOT changed"
            "\n(the bot keeps working wherever it is pointing now)."
            "\nFix the deployment first: the output above shows what each URL answered."
        )

    # Updates queued while the webhook was pointing somewhere broken are
    # stale: delivering them would answer messages from hours ago.
    params = {
        "url": url ,
        "allowed_updates": json.dumps(["message"]) ,
        "drop_pending_updates": "true" ,
    }
    if secret:
        params["secret_token"] = secret
    else:
        print("Warning: WEBHOOK_SECRET is not set, the webhook URL will accept updates from anyone")

    print(f"\nSetting webhook to {url}")
    print(call(token , "setWebhook" , **params))


if __name__ == "__main__":
    main()
