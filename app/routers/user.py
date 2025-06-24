from fastapi import APIRouter, Depends, HTTPException

from app.core.dependencies import get_db, get_current_user
from app.models import User
from app.schemas import UserRead

from sqlalchemy.ext.asyncio import AsyncSession


router = APIRouter()


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
