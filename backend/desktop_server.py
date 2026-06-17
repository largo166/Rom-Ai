import os

import uvicorn

from app.config import BASE_DIR, LOG_DIR
from main import app


def main() -> None:
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    (BASE_DIR / "uploads").mkdir(parents=True, exist_ok=True)
    (BASE_DIR / "cloud").mkdir(parents=True, exist_ok=True)

    port = int(os.environ.get("ROM_AI_BACKEND_PORT", "8000"))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info", reload=False)


if __name__ == "__main__":
    main()
