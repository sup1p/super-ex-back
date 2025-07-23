# app/main.py  (полностью асинхронный вариант)

from fastapi import FastAPI, HTTPException, Depends, status, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas import RegisterRequest, LoginRequest, TokenResponse
from app.models import User
from app.core.database import AsyncSessionLocal, engine, Base
from app.core.security import hash_password, verify_password, create_access_token
from app.routers import chat, note, translate, user, tools, smtp, voice
from fastapi.security import OAuth2PasswordRequestForm
import redis.asyncio as aioredis
from app import redis_client
from contextlib import asynccontextmanager

from pydantic import BaseModel
import os
from dotenv import load_dotenv
import logging

logging.basicConfig(
    level=logging.INFO,  # или DEBUG для подробных логов
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

load_dotenv()


# ────────────────────────────── DB (инициализация) ─────────────────────────────
# Если нужны миграции — используй Alembic; ниже — временное создание таблиц.
async def init_models() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# ────────────────────────────── FastAPI ────────────────────────────────────────


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
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
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


# ────────────────────────────── DI: сессия БД ──────────────────────────────────
async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


# ────────────────────────────── Auth endpoints ────────────────────────────────
@app.post("/auth/register", status_code=status.HTTP_201_CREATED)
async def register(data: RegisterRequest, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(User).where(User.email == data.email))
    if res.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="User already exists")

    user = User(
        email=data.email, hashed_password=hash_password(data.password), name=data.name
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return "Success"


@app.post("/auth/token", response_model=TokenResponse)
async def login(
    data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    res = await db.execute(select(User).where(User.email == data.username))
    user = res.scalar_one_or_none()
    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    return TokenResponse(access_token=create_access_token(str(user.id)))


@app.post("/auth/login", response_model=TokenResponse)
async def login(
    data: LoginRequest, db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    res = await db.execute(select(User).where(User.email == data.email))
    user = res.scalar_one_or_none()
    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    return TokenResponse(access_token=create_access_token(str(user.id)))


AI_TOKEN_LIMIT = os.getenv("AI_TOKEN_LIMIT")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
REDIRECT_URI = "http://localhost:3000/auth/callback"
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")


class Code(BaseModel):
    code: str


# ────────────────────────────── Misc ───────────────────────────────────────────
@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Hello"}


# ────────────────────────────── Startup hook ──────────────────────────────────
# Уберите все @app.on_event("startup") и @app.on_event("shutdown").


# ────────────────────────────── Lifespan ──────────────────────────────────────


app.include_router(chat.router)
app.include_router(note.router)
app.include_router(translate.router)
app.include_router(user.router)
app.include_router(tools.router)
app.include_router(smtp.router)
app.include_router(voice.router)
