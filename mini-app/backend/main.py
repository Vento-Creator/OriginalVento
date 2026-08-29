from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
import time
from dotenv import load_dotenv

load_dotenv()

from db import get_pool, close_pool


@asynccontextmanager
async def lifespan(app):
    """App ishga tushganda pool ochish, to'xtaganda yopish."""
    await get_pool()
    yield
    await close_pool()


app = FastAPI(title="Vento Mini App API", version="1.0.0", lifespan=lifespan)

# CORS
allowed_origins_env = os.getenv("VENTO_ALLOWED_ORIGINS", "")
allowed_origins = [o.strip() for o in allowed_origins_env.split(",") if o.strip()] if allowed_origins_env else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from routers import users, subscription, commands, admin, stats

app.include_router(users.router, prefix="/api/users", tags=["Users"])
app.include_router(subscription.router, prefix="/api/subscription", tags=["Subscription"])
app.include_router(commands.router, prefix="/api/commands", tags=["Commands"])
app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])
app.include_router(stats.router, prefix="/api/stats", tags=["Stats"])


@app.get("/")
async def root():
    return {"status": "ok", "message": "Vento Mini App API is running"}


@app.get("/health")
async def health():
    return {"status": "healthy", "timestamp": int(time.time())}
