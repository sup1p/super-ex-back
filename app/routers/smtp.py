from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.models import User
from app.schemas import RegisterRequest

from app.core.dependencies import get_db, AsyncSession
from app.core.security import (
    generate_email_token,
    verify_email_token,
    send_confirmation_email,
    hash_password,
)


router = APIRouter()


@router.post("/auth/pre-register", tags=["smtp"])
async def pre_register(data: RegisterRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalars().first()
    if user:
        raise HTTPException(status_code=400, detail="Email уже используется")

    # создаём токен с именем, email и хешированным паролем
    payload = {
        "name": data.name,
        "email": data.email,
        "hashed_password": hash_password(data.password),
    }
    token = generate_email_token(payload)

    await send_confirmation_email(data.email, token)
    return {"message": "Письмо с подтверждением отправлено"}


@router.get("/auth/confirm", tags=["smtp"], status_code=200)
async def confirm_registration(token: str, db: AsyncSession = Depends(get_db)):
    try:
        payload = verify_email_token(token)
        email = payload["email"]
    except Exception:
        raise HTTPException(status_code=400, detail="Недействительный токен")

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalars().first()
    if user:
        return "Email already confimed"

    user = User(
        email=email,
        name=payload["name"],
        hashed_password=payload["hashed_password"],
        is_oauth_user=False,
    )

    db.add(user)
    await db.commit()
    await db.refresh(user)

    return {"message": "Почта подтверждена, пользователь зарегистрирован"}


@router.post("/auth/resend", tags=["smtp"])
async def resend_confirmation(email: str):
    # Поиск по временной сессии/памяти не нужен — просто повторно шлём
    token = generate_email_token({"email": email})
    await send_confirmation_email(email, token)
    return {"message": "Письмо повторно отправлено"}
