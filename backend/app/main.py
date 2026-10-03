from fastapi import FastAPI

from app.api.routes import auth, projects, tests

app = FastAPI(
    title="Aspen API",
    version="0.1.0",
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