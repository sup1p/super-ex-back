from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, delete

from app.models import User, PendingUser
from app.schemas import RegisterRequest

from app.core.dependencies import get_db, AsyncSession
from app.core.security import (
    generate_email_token,
    verify_email_token,
    send_confirmation_email,
    hash_password,
)
from datetime import datetime, timedelta


router = APIRouter()


@router.post("/auth/pre-register", tags=["smtp"])
async def pre_register(data: RegisterRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalars().first()
    if user:
        raise HTTPException(status_code=400, detail="Email уже используется")

    result = await db.execute(
        select(PendingUser).where(PendingUser.email == data.email)
    )
    pending = result.scalars().first()
    if pending:
        raise HTTPException(
            status_code=400, detail="Письмо уже отправлено, проверьте почту"
        )

    pending = PendingUser(
        email=data.email,
        name=data.name,
        hashed_password=hash_password(data.password),
        created_at=datetime.utcnow(),
    )

    db.add(pending)
    await db.commit()
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
    await db.execute(delete(PendingUser).where(PendingUser.email == email))
    await db.commit()
    await db.refresh(user)

    return {"message": "Почта подтверждена, пользователь зарегистрирован"}


@router.post("/auth/resend", tags=["smtp"])
async def resend_confirmation(email: str, db: AsyncSession = Depends(get_db)):
    result = db.execute(select(PendingUser).where(PendingUser.email == email))
    pending = result.scalars().first()
    if not pending:
        raise HTTPException(status_code=404, detail="No such a pending user")

    payload = {
        "name": pending.name,
        "email": pending.email,
        "hashed_password": pending.hashed_password,
    }

    token = generate_email_token(payload)
    await send_confirmation_email(email, token)
    return {"message": "Письмо повторно отправлено"}
