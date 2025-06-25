from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from jose import jwt
import httpx
import os

from app.core.database import get_db
from app.models import User
from app.core.security import create_access_token

router = APIRouter()

# .env или конфигурация
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI")
FRONTEND_URL = os.getenv(
    "FRONTEND_URL", "http://localhost:5173"
)  # можно вынести отдельно


@router.get("/auth/google/callback")
async def google_callback(code: str, db: Session = Depends(get_db)):
    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code",
    }

    async with httpx.AsyncClient() as client:
        token_resp = await client.post(token_url, data=data)
        if token_resp.status_code != 200:
            raise HTTPException(
                status_code=400, detail="Failed to fetch token from Google"
            )
        token_data = token_resp.json()

    id_token = token_data.get("id_token")
    if not id_token:
        raise HTTPException(status_code=400, detail="Missing ID token")

    # 2. Распаковываем ID token без проверки подписи (в проде — можно верифицировать)
    payload = jwt.get_unverified_claims(id_token)
    email = payload.get("email")
    name = payload.get("name")
    avatar_url = payload.get("picture")

    if not email:
        raise HTTPException(status_code=400, detail="Email not found in token")

    # 3. Ищем пользователя или создаем
    user = db.query(User).filter(User.email == email).first()
    if not user:
        user = User(
            email=email,
            name=name,
            avatar_url=avatar_url,
            is_oauth_user=True,
            hashed_password=None,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    access_token = create_access_token(str(user.id))

    return RedirectResponse(f"{FRONTEND_URL}/oauth-callback?token={access_token}")
