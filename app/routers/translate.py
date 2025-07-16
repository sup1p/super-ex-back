from fastapi import APIRouter, Depends, Query, Body, HTTPException

from googletrans import Translator
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User

from app.core.dependencies import get_db, get_current_user

from typing import List

from app.token_limit import check_translate_limit

from app.schemas import TranslateRequest

from pydantic import BaseModel

import os
import logging
import app.redis_client

logger = logging.getLogger(__name__)


router = APIRouter()
translator = Translator()


@router.post("/translate", tags=["Translate"])
async def translate(
    text: str = Query(..., description="Text to translate"),
    src: str = Query("ru", description="Source language"),
    dest: str = Query("en", description="Destination language"),
    current_user: User = Depends(get_current_user),
):
    result = await translator.translate(text, src=src, dest=dest)
    return {"translated_text": result.text}


@router.post("/translate-page", tags=["Translate"])
async def translate_page(
    texts: List[str] = Body(..., embed=True, description="List of texts to translate"),
    dest: str = Query("en", description="Destination language"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    print("Text came to translate: ")
    print(texts)
    src = "auto"
    translated = []
    for text in texts:
        result = await translator.translate(text, src=src, dest=dest)
        translated.append(result.text)
    print("translated_texts" + ":")
    print(translated)
    return {"translated_texts": translated}


@router.post("/translate-new", tags=["Translate"])
async def translate_new(
    data: TranslateRequest,
    current_user: User = Depends(get_current_user),
):
    text = data.text
    src = data.src
    dest = data.dest
    user_id = str(current_user.id)
    symbols_needed = len(text)
    today = __import__("datetime").date.today().isoformat()
    key = f"translate_symbols:{user_id}:{today}"
    redis = app.redis_client.redis
    current = await redis.get(key) if redis else 0
    current = int(current) if current else 0
    left = int(os.getenv("TRANSLATE_SYMBOLS_LIMIT")) - (current + symbols_needed)
    logger.info(
        f"[TranslateNew] user_id={user_id} | current={current} | needed={symbols_needed} | left={left}"
    )

    # Проверяем лимит только логически (не инкрементируем)
    if current + symbols_needed > int(os.getenv("TRANSLATE_SYMBOLS_LIMIT")):
        logger.warning(
            f"[TranslateNew] LIMIT EXCEEDED: user_id={user_id} | attempted={current + symbols_needed} | limit={os.getenv('TRANSLATE_SYMBOLS_LIMIT')}"
        )
        raise HTTPException(status_code=429, detail="Token limit exceeded")

    # Пробуем перевод
    try:
        result = await translator.translate(text, src=src, dest=dest)
    except Exception as e:
        logger.error(f"[TranslateNew] Translation failed: {e}")
        raise HTTPException(status_code=500, detail="Translation failed")

    # Только если перевод успешен — инкрементируем лимит
    await check_translate_limit(redis, user_id, symbols_needed)

    return {"translated_text": result.text}
