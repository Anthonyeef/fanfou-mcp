"""Mint a personal bearer token for an existing Fanfou access token (admin / migration / testing).
Needs KV env (KV_REST_API_URL/TOKEN) and FANFOU_API_KEY/SECRET + FANFOU_OAUTH_TOKEN[_SECRET] in env.
Prints only the new personal token."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import creds
from fanfou_api import Fanfou

user = creds.UserToken(os.environ["FANFOU_OAUTH_TOKEN"], os.environ["FANFOU_OAUTH_TOKEN_SECRET"])
uid = "unverified"
if "--no-verify" not in sys.argv:
    app = creds.app_credentials()
    uid = str(Fanfou(app.consumer_key, app.consumer_secret, user.token, user.token_secret)
              .get("/account/verify_credentials.json", mode="lite")["id"])
print(creds.issue_personal_token(user, uid))
