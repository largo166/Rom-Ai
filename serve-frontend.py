from __future__ import annotations

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parent / "frontend" / "dist"


class SpaHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def send_head(self):
        path = ROOT / self.path.lstrip("/").split("?", 1)[0]
        if not path.exists() and "." not in path.name:
            self.path = "/index.html"
        return super().send_head()


if __name__ == "__main__":
    log_path = Path(__file__).resolve().parent / "logs" / "frontend-static.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        server = ThreadingHTTPServer(("127.0.0.1", 5175), SpaHandler)
        log_path.write_text("RMO-AI frontend serving at http://127.0.0.1:5175\n", encoding="utf-8")
        server.serve_forever()
    except Exception as exc:
        log_path.write_text(f"frontend static server failed: {exc}\n", encoding="utf-8")
        raise
