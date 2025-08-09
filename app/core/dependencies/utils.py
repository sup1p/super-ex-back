from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from jose import jwt, JWTError

from app.models import User
from app.core.config import settings
from app.core.database import get_db

import tiktoken
import re
from datetime import date


VOICE_SYMBOLS_LIMIT = settings.voice_symbols_limit


def count_tokens(text: str, model: str = "gpt-3.5-turbo") -> int:
    enc = tiktoken.encoding_for_model(model)
    return len(enc.encode(text))


def is_valid_text(text: str) -> bool:
    # Проверяем минимальную длину оригинального текста
    if len(text.strip()) < 5:
        return False

    # Убираем пробелы и символы, оставляем только буквы
    cleaned = re.sub(r"[^\wа-яА-ЯёЁ]", "", text)

    # Игнорируем слишком короткие или непонятные тексты
    if len(cleaned) < 4:
        return False

    # Игнорируем если нет хотя бы 2 букв подряд
    if not re.search(r"[a-zA-Zа-яА-ЯёЁ]{2,}", text):
        return False

    # Игнорируем часто встречающиеся фразы при отсутствии речи
    common_noise_phrases = ["thank you", "thanks", "thank", "you", "thank you."]
    if text.lower().strip() in common_noise_phrases:
        return False

    return True


async def get_current_user(
    token: str = Depends(settings.oauth2_scheme), db: AsyncSession = Depends(get_db)
) -> User:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        user_id: str = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


async def get_voice_summary_within_limit(redis, user_id: str, text: str) -> str:
    """
    Возвращает часть текста, которую можно озвучить, не превышая лимит символов на сегодня.
    Если лимита хватает — возвращает весь текст.
    Если нет — только часть, которая помещается в лимит.
    """

    today = date.today().isoformat()
    key = f"voice_symbols:{user_id}:{today}"
    current = await redis.get(key)
    current = int(current) if current else 0
    limit = int(VOICE_SYMBOLS_LIMIT)
    remaining = limit - current
    if remaining <= 0:
        return ""
    return text[:remaining]
