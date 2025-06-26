from fastapi import Depends, HTTPException, status, WebSocket, WebSocketDisconnect
from jose import jwt, JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models import User
from dotenv import load_dotenv
import logging
import base64
import json
import os
import re
import tempfile
from edge_tts.exceptions import NoAudioReceived

from ..services.voice import (
    IntentAgent,
    ActionAgent,
    MediaAgent,
    TextGenerationAgent,
    synthesize_speech_async,
    transcribe_audio_async,
)

load_dotenv()

voice_map = {
    "ru": "ru-RU-DmitryNeural",
    "en": "en-US-GuyNeural",
    "de": "de-DE-ConradNeural",
    "fr": "fr-FR-HenriNeural",
    "es": "es-ES-AlvaroNeural",
    "kk": "kk-KZ-DauletNeural",
}


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


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


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


# --- вспомогательные функции -------------------------------------------------

CMD_JSON_RE = re.compile(r"^\s*\{.*\}\s*$", re.S)  # грубая проверка JSON


# --- основная точка входа -----------------------------------------------------


async def handle_voice_websocket(websocket: WebSocket):
    await websocket.accept()
    last_text = ""
    user_tabs = []

    try:
        while True:
            msg = await websocket.receive()
            if "bytes" in msg:
                audio_bytes = msg["bytes"]

                if not audio_bytes:
                    continue

                print("Audio received")

                with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as f:
                    f.write(audio_bytes)
                    audio_path = f.name

                result = await transcribe_audio_async(audio_path)
                os.remove(audio_path)
                text = result.get("text", "").strip()

                print(f"Transcribed text: {text}")

                if not is_valid_text(text) or text == last_text:
                    print(f"Пропускаем бессмысленный текст: {text}")
                    continue
                last_text = text

                lang = result.get("language", "en")
                intent = await IntentAgent.detect_intent(text)

                avg_logprob = result.get("avg_logprob", -1.0)
                no_speech_p = result.get("no_speech_prob", 1.0)
                lang = result.get("language", "en")
                confidence = 1 - max(no_speech_p, -avg_logprob)

                if intent == "command":
                    cmd = await ActionAgent.handle_command(
                        text, lang, user_tabs, confidence
                    )
                    print(f"AI responded with command: {cmd}")
                    await websocket.send_json({"command": cmd})
                    continue
                elif intent == "media":
                    cmd = await MediaAgent.handle_media_command(text, lang)
                    print(f"AI responded with media command: {cmd}")
                    await websocket.send_json(cmd)
                    continue
                elif intent == "question":
                    answer = await ActionAgent.handle_question(text, lang)
                    print(f"AI responded with default answer: {answer}")
                elif intent == "generate_text":
                    result = await TextGenerationAgent.handle_generate_text(text, lang)
                    print(f"AI generated text or note: {result}")
                    await websocket.send_json(result)
                    continue
                else:
                    answer = "Пожалуйста, повторите команду."
                    print("AI could not understand request")

                voice = voice_map.get(lang, "en-US-GuyNeural")
                with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
                    tts_path = f.name
                try:
                    await synthesize_speech_async(answer, voice, tts_path)
                except NoAudioReceived:
                    answer = "Ошибка синтеза речи: не удалось получить аудио. Попробуйте другой язык или переформулируйте запрос."
                    print("[TTS] No audio received from edge_tts.")
                    audio_b64 = ""
                except Exception as tts_e:
                    logging.error(f"TTS error: {tts_e}", exc_info=True)
                    answer = f"Ошибка синтеза речи: {tts_e}"
                    audio_b64 = ""
                else:
                    with open(tts_path, "rb") as f:
                        audio_b64 = base64.b64encode(f.read()).decode()
                    os.remove(tts_path)

                await websocket.send_json(
                    {"text": answer, "language": lang, "audio_base64": audio_b64}
                )

            elif "text" in msg:
                try:
                    parsed = json.loads(msg["text"])
                    if isinstance(parsed, dict) and "tabs" in parsed:
                        user_tabs = parsed["tabs"]
                except json.JSONDecodeError:
                    pass

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logging.error(f"WebSocket error: {e}", exc_info=True)
        try:
            await websocket.close(code=1011, reason="Server error")
        except:
            pass
