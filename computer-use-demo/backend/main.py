from __future__ import annotations

import uvicorn

from app.api import app


def run():
    uvicorn.run(app, host="0.0.0.0", port=8080, reload=False)


if __name__ == "__main__":
    run()


