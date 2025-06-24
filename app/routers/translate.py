from fastapi import APIRouter, Depends, Query, Body

from googletrans import Translator
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User

from app.core.dependencies import get_db, get_current_user

from typing import List


router = APIRouter()
translator = Translator()


@router.post("/translate", tags=["Translate"])
async def translate(
    text: str = Query(..., description="Text to translate"),
    src: str = Query("ru", description="Source language"),
    dest: str = Query("en", description="Destination language"),
    db: AsyncSession = Depends(get_db),
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
