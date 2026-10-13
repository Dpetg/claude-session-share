"""テスト用の自前 git サーバ (git http-backend を HTTP / HTTPS で公開する)。

    python3 tests/git_server.py <リポジトリの親ディレクトリ> <ポート> [証明書.pem 鍵.pem]

標準ライブラリと git だけで動く。push も受け付ける (http.receivepack)。
"""
import os
import ssl
import subprocess
import sys
from wsgiref.simple_server import WSGIRequestHandler, make_server

ROOT, PORT = sys.argv[1], int(sys.argv[2])
BACKEND = subprocess.run(["git", "--exec-path"], capture_output=True, text=True).stdout.strip() + "/git-http-backend"


def app(environ, start_response):
    length = int(environ.get("CONTENT_LENGTH") or 0)
    body = environ["wsgi.input"].read(length) if length else b""
    env = {
        "GIT_PROJECT_ROOT": ROOT,
        "GIT_HTTP_EXPORT_ALL": "1",
        "REMOTE_USER": "tester",
        "PATH_INFO": environ.get("PATH_INFO", ""),
        "QUERY_STRING": environ.get("QUERY_STRING", ""),
        "REQUEST_METHOD": environ["REQUEST_METHOD"],
        "CONTENT_TYPE": environ.get("CONTENT_TYPE", ""),
        "CONTENT_LENGTH": str(len(body)),
        "HTTP_CONTENT_ENCODING": environ.get("HTTP_CONTENT_ENCODING", ""),
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "http.receivepack",
        "GIT_CONFIG_VALUE_0": "true",
        "PATH": os.environ.get("PATH", ""),
    }
    out = subprocess.run([BACKEND], input=body, env=env, capture_output=True).stdout
    head, _, rest = out.partition(b"\r\n\r\n")
    status, headers = "200 OK", []
    for line in head.decode("latin-1").split("\r\n"):
        k, _, v = line.partition(":")
        if k.lower() == "status":
            status = v.strip()
        elif k:
            headers.append((k, v.strip()))
    start_response(status, headers)
    return [rest]


class Quiet(WSGIRequestHandler):
    def log_message(self, *a):
        pass


httpd = make_server("127.0.0.1", PORT, app, handler_class=Quiet)
if len(sys.argv) > 4:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(sys.argv[3], sys.argv[4])
    httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
httpd.serve_forever()
