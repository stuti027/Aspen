from fastapi import FastAPI

from app.api.routes import auth, projects, tests
from app.core.logging import setup_logging
from app.core.errors import global_exception_handler

setup_logging()
app = FastAPI(
    title="Aspen API",
    version="0.1.0",
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


@app.get("/health")
async def health_check():
    return {"status": "ok"}