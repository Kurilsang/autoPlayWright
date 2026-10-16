"""联调用回调接收器（演示/自测用，非产品代码）：把收到的回调落盘。

用法: python scripts/callback_sink.py --port 8788 --out reports/callback.json
"""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8788)
    parser.add_argument("--out", default="reports/callback.json")
    args = parser.parse_args()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - http.server 约定
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length).decode("utf-8", "ignore")
            with open(args.out, "w", encoding="utf-8") as fh:
                fh.write(raw)
            print(f"[sink] 收到回调 {len(raw)} 字节 → {args.out}", flush=True)
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *a):  # noqa: ANN002 - 静默
            pass

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"[sink] 监听 127.0.0.1:{args.port} → {args.out}", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
