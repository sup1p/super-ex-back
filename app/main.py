from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


from app.core.config import settings
from app.routers import auth, chat, note, translate, user, tools, smtp, voice, calendar
from app import redis_client

import redis.asyncio as aioredis
import logging
from contextlib import asynccontextmanager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


REDIS_URL = settings.redis_url


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Lifespan startup: initializing redis")
    redis_client.redis = await aioredis.from_url(REDIS_URL, decode_responses=True)
    print("Lifespan startup: redis initialized")
    yield
    print("Lifespan shutdown: closing redis")
    await redis_client.redis.close()
    print("Lifespan shutdown: redis closed")


app = FastAPI(
    title="Browser‑AI Backend",
    lifespan=lifespan,
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "chrome-extension://ibkkolnhabfjiggngeedojohemhkddjk",
        "http://localhost:3000",
        "https://yourmegan.me",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Hello"}


app.include_router(chat.router)
app.include_router(note.router)
app.include_router(translate.router)
app.include_router(user.router)
app.include_router(tools.router)
app.include_router(smtp.router)
app.include_router(voice.router)
app.include_router(calendar.router)
app.include_router(auth.router)
