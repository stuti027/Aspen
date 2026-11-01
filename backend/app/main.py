from fastapi import FastAPI

from app.api.routes import auth, projects, tests
from app.core.logging import setup_logging
from app.core.errors import global_exception_handler
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

setup_logging()
app = FastAPI(
    title="Aspen API",
    version="0.1.0",
)

BASE_DIR = Path(__file__).resolve().parent.parent

app.mount(
    "/static",
    StaticFiles(directory=BASE_DIR / "static"),
    name="static",
)

app.add_exception_handler(
    Exception,
    global_exception_handler,
)

app.include_router(
    auth.router,
    prefix="/api",
)

app.include_router(
    projects.router,
    prefix="/api",
)

app.include_router(
    tests.router,
    prefix="/api",
)

@app.get("/")
def read_root():
    return RedirectResponse(url="/docs")


@app.get("/health")
async def health_check():
    return {"status": "ok"}

backend_dir = Path(__file__).resolve().parent.parent 
app.mount("/static", StaticFiles(directory=str(backend_dir / "static")), name="static")