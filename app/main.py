# app/main.py  (полностью асинхронный вариант)

from fastapi import FastAPI, HTTPException, Depends, status, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas import RegisterRequest, LoginRequest, TokenResponse
from app.models import User
from app.core.database import AsyncSessionLocal, engine, Base
from app.core.security import hash_password, verify_password, create_access_token
from app.routers import chat, note, translate, user, tools, smtp
from fastapi.security import OAuth2PasswordRequestForm

from pydantic import BaseModel
import os
from dotenv import load_dotenv

load_dotenv()


# ────────────────────────────── DB (инициализация) ─────────────────────────────
# Если нужны миграции — используй Alembic; ниже — временное создание таблиц.
async def init_models() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# ────────────────────────────── FastAPI ────────────────────────────────────────
app = FastAPI(title="Browser‑AI Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # ⚠️ В проде укажи домены
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


load_dotenv()

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
REDIRECT_URI = "http://localhost:3000/auth/callback"


class Code(BaseModel):
    code: str


# ────────────────────────────── Misc ───────────────────────────────────────────
@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Hello"}


# ────────────────────────────── Startup hook ──────────────────────────────────
@app.on_event("startup")
async def on_startup() -> None:
    await init_models()


app.include_router(chat.router)
app.include_router(note.router)
app.include_router(translate.router)
app.include_router(user.router)
app.include_router(tools.router)
app.include_router(smtp.router)
