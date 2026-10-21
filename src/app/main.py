from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text

from app.database import engine
from app.rate_limit import limiter
from app.routes import application as application_routes
from app.routes import company as company_routes
from app.routes import user as user_routes

app = FastAPI(title="App")

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5500", "http://localhost:5500"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(user_routes.router)
app.include_router(company_routes.router)
app.include_router(application_routes.router)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    """Проверка для деплоя и docker healthcheck: приложение живо и база отвечает."""
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return {"status": "ok"}
