"""ローカルで開く画面。株価のダウンロード機能は付けない。"""

from __future__ import annotations

import json
import webbrowser
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from config import Settings, load_settings, save_settings
from db import connect, init_db, latest_ranking, latest_recorded_at
from engine import coin_payload, ranking_payload, start_update, STATUS

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
HOST = "127.0.0.1"
PORT = 8765

TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        return

    def _body(self, code: int, payload: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _json(self, data: dict, code: int = 200) -> None:
        self._body(code, json.dumps(data, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        data = json.loads(raw.decode() or "{}")
        return data if isinstance(data, dict) else {}

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        try:
            if parsed.path == "/api/ranking":
                self._json(ranking_payload())
                return
            if parsed.path == "/api/status":
                self._json(dict(STATUS))
                return
            if parsed.path == "/api/settings":
                self._json(asdict(load_settings()))
                return
            if parsed.path == "/api/coin":
                coin = (query.get("coin") or [""])[0]
                timeframe = (query.get("tf") or ["1d"])[0]
                if timeframe not in {"1d", "1w", "1M"}:
                    timeframe = "1d"
                rank = volume = None
                recorded = None
                with connect() as conn:
                    recorded, rows = latest_ranking(conn, 500)
                for row in rows:
                    if row["coin"] == coin:
                        rank = row["rank"]
                        volume = row["volume_24h"]
                        break
                if not coin:
                    self._json({"error": "銘柄がありません"}, 400)
                    return
                self._json(coin_payload(coin, timeframe, rank, volume, recorded))
                return
        except Exception as exc:  # noqa: BLE001
            self._json({"error": str(exc)}, 500)
            return
        self._file(parsed.path)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/update":
                started = start_update()
                self._json({"started": started, "status": dict(STATUS)})
                return
            if parsed.path == "/api/settings":
                current = load_settings()
                incoming = self._read_json()
                for key, value in incoming.items():
                    if hasattr(current, key) and key != "save_top":
                        setattr(current, key, type(getattr(current, key))(value))
                if "save_top" in incoming:
                    current.save_top = int(incoming["save_top"])
                save_settings(Settings(**{**asdict(load_settings()), **asdict(current)}))
                self._json(asdict(load_settings()))
                return
        except Exception as exc:  # noqa: BLE001
            self._json({"error": str(exc)}, 400)
            return
        self._json({"error": "not found"}, 404)

    def _file(self, path: str) -> None:
        relative = "index.html" if path in {"", "/"} else path.lstrip("/")
        file_path = (STATIC / relative).resolve()
        if not file_path.is_relative_to(STATIC.resolve()) or not file_path.is_file():
            self._body(404, b"not found", "text/plain; charset=utf-8")
            return
        self._body(200, file_path.read_bytes(), TYPES.get(file_path.suffix, "application/octet-stream"))


def main() -> None:
    init_db()
    with connect() as conn:
        if latest_recorded_at(conn) is None:
            start_update()
    url = f"http://{HOST}:{PORT}"
    print(f"仮想通貨テクニカルトレーナー: {url}")
    webbrowser.open(url)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
