from fastapi import APIRouter, Depends, WebSocket

from sqlalchemy import select
from app.core.database import get_db

from app.models import User
from app.schemas import TextRequest, SummaryRequest

from edge_tts.exceptions import NoAudioReceived

from app.core.dependencies.utils import get_current_user
from app.core.dependencies.web import voice_website_summary
from app.core.dependencies.voice import handle_voice_websocket

from app.core.config import settings
from app.services.voice.speech import synthesize_speech_async
import app.redis_client
from app.token_limit import check_voice_limit_only, increment_voice_limit

from jose import JWTError, jwt
import logging
import tempfile
import os
import base64


logger = logging.getLogger(__name__)
voice = settings.eleven_labs_voice_id

router = APIRouter()


@router.websocket("/websocket-voice")
async def websocket_voice(websocket: WebSocket):
    token = websocket.query_params.get("token")
    if not token:
        await websocket.send_json({"error": "No token provided"})
        await websocket.close()
        logger.error("WebSocket закрыт: не передан токен.")
        return
    async with get_db() as db:
        try:
            payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
            user_id: str = payload.get("sub")
            if not user_id:
                await websocket.send_json({"error": "Invalid token"})
                await websocket.close()
                logger.error("WebSocket закрыт: некорректный токен (нет user_id).")
                return
        except JWTError:
            await websocket.send_json({"error": "Invalid token"})
            await websocket.close()
            logger.error("WebSocket закрыт: некорректный токен (JWTError).")
            return
        result = await db.execute(select(User).where(User.id == int(user_id)))
        user = result.scalar_one_or_none()
        if not user:
            await websocket.send_json({"error": "User not found"})
            await websocket.close()
            logger.error(f"WebSocket закрыт: пользователь с id {user_id} не найден.")
            return

    await handle_voice_websocket(websocket, str(user_id))


@router.post("/tools/voice/selected", tags=["Tools"])
async def voice_text(
    voice_request: TextRequest, current_user: User = Depends(get_current_user)
):
    user_id = str(current_user.id)
    symbols_needed = len(voice_request.text)
    redis = app.redis_client.redis

    await check_voice_limit_only(redis, user_id, symbols_needed)

    text_to_voice = voice_request.text
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
        tts_path = f.name
    try:
        await synthesize_speech_async(text_to_voice, voice, tts_path)
    except NoAudioReceived:
        text_to_voice = "Error occured, could not synthesize text"
        logger.error("[TTS] No audio received from edge_tts.")
        audio_b64 = ""
    except Exception as tts_e:
        text_to_voice = "Error occured, could not synthesize text"
        logger.error(f"TTS error: {tts_e}", exc_info=True)
        audio_b64 = ""
    else:
        with open(tts_path, "rb") as f:
            audio_b64 = base64.b64encode(f.read()).decode()
        os.remove(tts_path)
    if audio_b64 == "":
        logger.info(
            f"Error occured and system could not synthesize text. Sent text to client: {text_to_voice}"
        )
        return {"text": text_to_voice}
    logger.info(f"Sent voiced text to client: {text_to_voice}")

    await increment_voice_limit(redis, user_id, symbols_needed)

    return {"text": text_to_voice, "audio_base64": audio_b64}


@router.post("/tools/voice/website_summary", tags=["Tools"])
async def voice_website_summary_route(
    data: SummaryRequest, current_user: User = Depends(get_current_user)
):
    return await voice_website_summary(data.url, current_user.id)
