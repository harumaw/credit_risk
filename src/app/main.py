from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.rate_limit import limiter
from app.routes import category as category_routes
from app.routes import expense as expense_routes
from app.routes import user as user_routes
from app.routes import goal as goal_routes
from app.routes import income as income_routes

app = FastAPI(title="App")

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5500", "http://localhost:5500"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(category_routes.router)
app.include_router(expense_routes.router)
app.include_router(user_routes.router)
app.include_router(goal_routes.router)
app.include_router(income_routes.router)