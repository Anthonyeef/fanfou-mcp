"""Local stand-in for the Upstash/Vercel KV REST API (SET [EX n], GET, GETDEL, DEL, TTL), for testing only.
Usage: python dev/mock_upstash.py [port]   then  KV_REST_API_URL=http://127.0.0.1:<port> KV_REST_API_TOKEN=dev
"""
import json, sys, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DATA = {}  # key -> (value, expires_at|None)
TOKEN = "dev"


def run(cmd):
    op, args = cmd[0].upper(), cmd[1:]
    now = time.time()
    for k in [k for k, (_, e) in DATA.items() if e and e < now]:
        DATA.pop(k)
    if op == "SET":
        ttl = int(args[3]) if len(args) >= 4 and args[2].upper() == "EX" else None
        DATA[args[0]] = (args[1], now + ttl if ttl else None)
        return "OK"
    if op == "GET":
        return DATA.get(args[0], (None,))[0]
    if op == "GETDEL":
        return DATA.pop(args[0], (None,))[0]
    if op == "DEL":
        return 1 if DATA.pop(args[0], None) else 0
    if op == "TTL":
        v = DATA.get(args[0])
        return -2 if not v else (-1 if not v[1] else int(v[1] - now))
    if op == "KEYS":
        return list(DATA)
    raise ValueError("unsupported command " + op)


class H(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.headers.get("Authorization") != "Bearer " + TOKEN:
            return self._out(401, {"error": "Unauthorized"})
        try:
            self._out(200, {"result": run(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))})
        except Exception as e:
            self._out(400, {"error": str(e)})

    def _out(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1]) if len(sys.argv) > 1 else 8079), H).serve_forever()
