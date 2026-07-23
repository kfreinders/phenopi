from __future__ import annotations

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from gui.config import APP_DIR
from gui.routes import schedule_api, scheduler


def create_app() -> FastAPI:
    app = FastAPI(title="Phenopi GUI")

    app.include_router(schedule_api.router)
    app.include_router(scheduler.router)

    react_dir = APP_DIR / "react-dist"
    assets_dir = react_dir / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def react_app(path: str) -> FileResponse:
        index = react_dir / "index.html"
        if not index.exists():
            raise HTTPException(
                status_code=503,
                detail="React GUI has not been built. Run npm run build in gui/frontend.",
            )
        return FileResponse(index)

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
