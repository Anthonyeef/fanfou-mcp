"""Minimal Fanfou OAuth1 client.

Fanfou quirk: requests go over https (box egress blocks port 80), but the OAuth1
signature base string MUST use the http:// URL, otherwise the server answers
"Invalid signature. Expected basestring is GET&http%3A%2F%2F...".
Note: the api gateway returns nginx 404 for a curl/* User-Agent, so we set our own UA.
"""
import base64, hashlib, hmac, json, os, secrets, time
import urllib.error, urllib.parse, urllib.request

API = "api.fanfou.com"
UA = "fanfou-mcp-box/0.1 (Python-urllib)"


def _q(s):
    return urllib.parse.quote(str(s), safe="~")


class FanfouError(Exception):
    pass


class Fanfou:
    def __init__(self, ck=None, cs=None, tok=None, ts=None):
        self.ck = ck or os.environ.get("FANFOU_API_KEY", "")
        self.cs = cs or os.environ.get("FANFOU_API_SECRET", "")
        self.tok = tok or os.environ.get("FANFOU_OAUTH_TOKEN", "")
        self.ts = ts or os.environ.get("FANFOU_OAUTH_TOKEN_SECRET", "")
        missing = [n for n, v in [("FANFOU_API_KEY", self.ck), ("FANFOU_API_SECRET", self.cs),
                                  ("FANFOU_OAUTH_TOKEN", self.tok), ("FANFOU_OAUTH_TOKEN_SECRET", self.ts)] if not v]
        if missing:
            raise FanfouError("missing env: " + ", ".join(missing))

    def _auth(self, method, path, params):
        p = {"oauth_consumer_key": self.ck, "oauth_nonce": secrets.token_hex(8),
             "oauth_signature_method": "HMAC-SHA1", "oauth_timestamp": str(int(time.time())),
             "oauth_version": "1.0", "oauth_token": self.tok}
        allp = {**p, **{k: str(v) for k, v in params.items()}}
        norm = "&".join("%s=%s" % (_q(k), _q(v)) for k, v in sorted(allp.items()))
        base = "&".join([method, _q("http://%s%s" % (API, path)), _q(norm)])
        key = ("%s&%s" % (_q(self.cs), _q(self.ts))).encode()
        p["oauth_signature"] = base64.b64encode(hmac.new(key, base.encode(), hashlib.sha1).digest()).decode()
        return "OAuth " + ", ".join('%s="%s"' % (k, _q(v)) for k, v in p.items())

    def request(self, method, path, params=None):
        params = {k: v for k, v in (params or {}).items() if v is not None and v != ""}
        hdr = {"Authorization": self._auth(method, path, params), "User-Agent": UA}
        url = "https://%s%s" % (API, path)
        data = None
        if method == "GET":
            if params:
                url += "?" + "&".join("%s=%s" % (_q(k), _q(v)) for k, v in params.items())
        else:
            data = "&".join("%s=%s" % (_q(k), _q(v)) for k, v in params.items()).encode()
            hdr["Content-Type"] = "application/x-www-form-urlencoded"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=data, method=method, headers=hdr), timeout=30) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            try:
                msg = json.loads(body).get("error", body)
            except Exception:
                msg = body[:300]
            raise FanfouError("HTTP %s: %s" % (e.code, msg))

    def get(self, path, **params):
        return self.request("GET", path, params)

    def post(self, path, **params):
        return self.request("POST", path, params)
