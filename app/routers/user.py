from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.core.dependencies.utils import get_current_user
from app.core.database import get_db
from app.models import User
from app.schemas import UserRead, ChangePasswordRequest, ForgotPasswordRequest
from app.core.security import (
    generate_email_token,
    send_change_pass_confirmation_email,
    verify_email_token,
    hash_password,
)

from sqlalchemy.ext.asyncio import AsyncSession


router = APIRouter()


@router.post("/user/pre-forgot-password", tags=["User"])
async def pre_forgot_password(
    data: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="No such a user")
    payload = {"email": user.email}
    token = generate_email_token(payload=payload)
    await send_change_pass_confirmation_email(user.email, token)
    return {"message": "Письмо с подтверждением отправлено"}


@router.post("/user/pre-change-password", tags=["User"])
async def pre_change_password(
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(User).where(User.email == current_user.email))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="No such a user")

    payload = {"email": user.email}

    token = generate_email_token(payload=payload)
    await send_change_pass_confirmation_email(user.email, token)
    return {"message": "Письмо с подтверждением отправлено"}


@router.post("/user/change-password", tags=["User"])
async def change_password(
    data: ChangePasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        payload = verify_email_token(data.token)
        email = payload["email"]
    except Exception:
        raise HTTPException(status_code=400, detail="Недействительный токен")
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=400, detail="No such a user")

    user.hashed_password = hash_password(data.new_password)
    await db.commit()
    return "Password successfully changed"


@router.post("/user/change-password/resend", tags=["User"])
async def resend_change_password(email: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalars().first()

    if not user:
        raise HTTPException(status_code=404, detail="No such a user")

    payload = {"email": user.email}

    token = generate_email_token(payload)
    await send_change_pass_confirmation_email(email, token)
    return {"message": "Email change password confirmation sent"}


@router.delete("/user/delete/{user_id}", tags=["User"])
async def user_delete(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user = await db.get(User, user_id)
    if user is None or user_id != current_user.id:
        raise HTTPException(status_code=404, detail="It is not your account")
    await db.delete(user)
    await db.commit()
    return "Deleted"


@router.get("/me", response_model=UserRead, tags=["User"])
async def get_me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
