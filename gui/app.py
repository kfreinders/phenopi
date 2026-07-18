from __future__ import annotations

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from gui.config import APP_DIR
from gui.routes import camera, schedule, scheduler


def create_app() -> FastAPI:
    app = FastAPI(title="Phenopi GUI")

    app.mount(
        "/static",
        StaticFiles(directory=APP_DIR / "static"),
        name="static",
    )

    app.include_router(schedule.router)
    app.include_router(camera.router)
    app.include_router(scheduler.router)

    return app


app = create_app()


def main() -> None:
    uvicorn.run(
        "gui.app:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )


if __name__ == "__main__":
    main()
