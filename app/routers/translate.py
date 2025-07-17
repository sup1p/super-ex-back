from fastapi import APIRouter, Depends, Query, Body, HTTPException

from googletrans import Translator
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User

from app.core.dependencies import get_db, get_current_user

from typing import List

from app.token_limit import check_translate_limit_only, increment_translate_limit

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
    user_id = str(current_user.id)
    symbols_needed = len(data.text)
    redis = app.redis_client.redis

    # Проверяем лимит (без инкремента)
    await check_translate_limit_only(redis, user_id, symbols_needed)

    logging.info(data.dest)
    # Пробуем перевод
    try:
        result = await translator.translate(
            text=data.text, src=data.src, dest=data.dest
        )
    except Exception as e:
        logger.error(f"[TranslateNew] Translation failed: {e}")
        raise HTTPException(status_code=500, detail="Translation failed")

    # Только если перевод успешен — инкрементируем лимит
    await increment_translate_limit(redis, user_id, symbols_needed)

    return {"translated_text": result.text}
