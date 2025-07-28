from fastapi import Depends, HTTPException, status, WebSocket, WebSocketDisconnect
from jose import jwt, JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models import User, Event
from dotenv import load_dotenv
import logging
import base64
import json
import os
import re
import tempfile
from edge_tts.exceptions import NoAudioReceived
from dotenv import load_dotenv
import asyncio
import tiktoken
from app.token_limit import (
    check_ai_limit_only,
    increment_ai_limit,
    check_voice_limit_only,
    increment_voice_limit,
)
import app.redis_client

from app.services import summarize

from ..services.voice import (
    IntentAgent,
    ActionAgent,
    MediaAgent,
    TextGenerationAgent,
    synthesize_speech_async,
    transcribe_audio_async,
    needs_web_search,
    process_web_search_results,
    CalendarAgent,
)

import logging
import requests
import aiohttp

load_dotenv()
logger = logging.getLogger(__name__)


voice_map = {
    "ru": "ru-RU-DmitryNeural",
    "en": "en-US-GuyNeural",
    "de": "de-DE-ConradNeural",
    "fr": "fr-FR-HenriNeural",
    "es": "es-ES-AlvaroNeural",
    "kk": "kk-KZ-DauletNeural",
}


SERPER_API_KEY = os.getenv("SERPER_API_KEY")


def count_tokens(text: str, model: str = "gpt-3.5-turbo") -> int:
    enc = tiktoken.encoding_for_model(model)
    return len(enc.encode(text))


async def fetch_website(website_url: str):
    url = "https://scrape.serper.dev"
    payload = {"url": website_url}
    headers = {
        "X-API-KEY": SERPER_API_KEY,  # Вставь свой ключ
        "Content-Type": "application/json",
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payload) as response:
            result = await response.text()
            return result


async def get_voice_summary_within_limit(redis, user_id: str, text: str) -> str:
    """
    Возвращает часть текста, которую можно озвучить, не превышая лимит символов на сегодня.
    Если лимита хватает — возвращает весь текст.
    Если нет — только часть, которая помещается в лимит.
    """
    from app.token_limit import VOICE_SYMBOLS_LIMIT
    from datetime import date

    today = date.today().isoformat()
    key = f"voice_symbols:{user_id}:{today}"
    current = await redis.get(key)
    current = int(current) if current else 0
    limit = int(VOICE_SYMBOLS_LIMIT)
    remaining = limit - current
    if remaining <= 0:
        return ""
    return text[:remaining]


async def voice_website_summary(website_url: str, current_user_id: str):
    user_id = str(current_user_id)
    symbols_needed = 100
    redis = app.redis_client.redis

    await check_voice_limit_only(redis, user_id, symbols_needed)

    data_to_voice = await fetch_website(website_url)

    try:
        parsed = json.loads(data_to_voice)
        if isinstance(parsed, dict) and "text" in parsed:
            data_to_voice = parsed["text"]
    except Exception:
        pass  # if not JSON — leave as is

    if len(data_to_voice) > 1000:
        truncated_data_to_voice = data_to_voice[:10000]

        summarized_text_to_voice = await summarize.summarize_text_full(
            truncated_data_to_voice, 2000
        )

        summarized_text_to_voice = await get_voice_summary_within_limit(
            redis, user_id, summarized_text_to_voice
        )

    else:
        truncated_data_to_voice = data_to_voice
        summarized_text_to_voice = truncated_data_to_voice

    voice = os.getenv("ELEVEN_LABS_VOICE_ID")
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
        tts_path = f.name
    try:
        await synthesize_speech_async(summarized_text_to_voice, voice, tts_path)
    except NoAudioReceived:
        summarized_text_to_voice = "Error occured, could not synthesize text"
        logger.error("[TTS] No audio received from edge_tts.")
        audio_b64 = ""
    except Exception as tts_e:
        summarized_text_to_voice = "Error occured, could not synthesize text"
        logger.error(f"TTS error: {tts_e}", exc_info=True)
        audio_b64 = ""
    else:
        with open(tts_path, "rb") as f:
            audio_b64 = base64.b64encode(f.read()).decode()
        os.remove(tts_path)
    if audio_b64 == "":
        logger.info(
            f"Error occured and system could not synthesize text. Sent text to client: {summarized_text_to_voice}"
        )
        return {"text": summarized_text_to_voice}
    logger.info(f"Sent voiced text to client: {summarized_text_to_voice}")

    await increment_voice_limit(redis, user_id, len(summarized_text_to_voice) + 50)

    return {"text": summarized_text_to_voice, "audio_base64": audio_b64}


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


async def handle_voice_websocket(websocket: WebSocket, user_id: str):
    await websocket.accept()
    user_tabs = []

    user_id = str(user_id)
    redis = app.redis_client.redis

    logger = logging.getLogger(__name__)

    try:
        while True:
            msg = await websocket.receive()
            if "bytes" in msg:
                audio_bytes = msg["bytes"]

                # ГЛОБАЛЬНАЯ ПРОВЕРКА ЛИМИТОВ
                try:
                    await check_ai_limit_only(redis, user_id, 1)
                    await check_voice_limit_only(redis, user_id, 1)
                except HTTPException as e:
                    if e.status_code == 429:
                        await websocket.send_json(
                            {"error": "Token or voice limit exceeded"}
                        )
                        continue
                    else:
                        raise

                if not audio_bytes:
                    logger.info("Пустой аудиофайл получен, пропуск.")
                    continue

                logger.info("Audio received")

                with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as f:
                    f.write(audio_bytes)
                    audio_path = f.name

                logger.info("Calling transcribe_audio_async")
                try:
                    result = await transcribe_audio_async(audio_path)
                except Exception as e:
                    logger.error(f"Error in transcribe_audio_async: {e}", exc_info=True)
                    continue
                logger.info("transcribe_audio_async finished")
                os.remove(audio_path)
                text = result.get("text", "").strip()

                logger.info(f"Transcribed text: {text}")

                if not is_valid_text(text):
                    logger.info(f"Пропускаем бессмысленный текст: {text}")
                    continue

                lang = result.get("language", "en")

                # CHECK FOR TOKENS BEFORE DETECTING INTENT
                tokens_needed_for_detect_intent = 500
                await check_ai_limit_only(
                    redis, user_id, tokens_needed_for_detect_intent
                )

                intent = await IntentAgent.detect_intent(text)
                logger.info(f"Detected intent: {intent}")

                lang = result.get("language", "en")

                if intent == "command":
                    # CHECK FOR TOKENS BEFORE COMMAND EXECUTION
                    tokens_in_command = count_tokens(text)

                    tokens_needed_for_handle_command = (
                        tokens_in_command + 500
                    )  # 500 is tokens for tabs

                    try:
                        await check_ai_limit_only(
                            redis, user_id, tokens_needed_for_handle_command
                        )
                    except HTTPException as e:
                        if e.status_code == 429:
                            await websocket.send_json({"error": "Token limit exceeded"})
                            continue
                        else:
                            raise

                    cmd = await ActionAgent.handle_command(text, lang, user_tabs)
                    logger.info(f"AI responded with command: {cmd}")
                    answer = cmd.get("answer", "")

                    tokens_in_answer = count_tokens(answer)

                    await increment_ai_limit(
                        redis, user_id, tokens_needed_for_handle_command
                    )
                    await increment_ai_limit(redis, user_id, tokens_in_answer)

                    # По умолчанию пустые значения
                    audio_b64 = ""

                    # Синтезируем озвучку только если есть ответ
                    if len(answer) > 0:
                        await check_voice_limit_only(redis, user_id, len(answer))

                        voice = os.getenv("ELEVEN_LABS_VOICE_ID")
                        with tempfile.NamedTemporaryFile(
                            delete=False, suffix=".mp3"
                        ) as f:
                            tts_path = f.name
                        try:
                            await synthesize_speech_async(answer, voice, tts_path)
                        except Exception as tts_e:
                            logger.error(f"TTS error: {tts_e}", exc_info=True)
                            audio_b64 = ""
                        else:
                            with open(tts_path, "rb") as f:
                                audio_b64 = base64.b64encode(f.read()).decode()
                            os.remove(tts_path)

                    response_json = {
                        "answer": answer,
                        "audio_base64": audio_b64,
                        "command": cmd,
                    }

                    await increment_voice_limit(redis, user_id, len(answer))

                    logger.info(f"Sending command response JSON: {response_json}")
                    await websocket.send_json(response_json)
                    continue
                elif intent == "media":
                    # CHECK FOR TOKENS BEFOREM MEDIA EXECUTION
                    tokens_in_media = count_tokens(text)

                    tokens_needed_for_handle_media = (
                        tokens_in_media + 500
                    )  # 500 is tokens for tabs

                    try:
                        await check_ai_limit_only(
                            redis, user_id, tokens_needed_for_handle_media
                        )
                    except HTTPException as e:
                        if e.status_code == 429:
                            await websocket.send_json({"error": "Token limit exceeded"})
                            continue
                        else:
                            raise

                    cmd = await MediaAgent.handle_media_command(text, lang)
                    tokens_in_cmd = count_tokens(cmd)

                    await increment_ai_limit(
                        redis, user_id, tokens_needed_for_handle_media
                    )
                    await increment_ai_limit(redis, user_id, tokens_in_answer)

                    logger.info(f"AI responded with media command: {cmd}")
                    await websocket.send_json(cmd)
                    continue
                elif intent == "summarize_webpage":
                    # Найти активную вкладку
                    active_tab = next(
                        (tab for tab in user_tabs if tab.get("active")), None
                    )
                    url = active_tab["url"] if active_tab else ""
                    answer = await voice_website_summary(url, user_id)

                    logger.info(
                        f"AI responded with website summary: {answer.get('text', '')}"
                    )

                    await websocket.send_json(
                        {
                            "text": answer.get("text", ""),
                            "audio_base64": answer.get("audio_base64", ""),
                        }
                    )

                    logger.info("Sent TTS response for text")
                    continue
                elif intent == "question":
                    tokens_in = count_tokens(text)
                    needs_search, search_query = await needs_web_search(text)
                    if needs_search and search_query:
                        logger.info(f"Требуется веб-поиск для запроса: {search_query}")
                        tokens_in += 500  # добавляем 500 токенов за web search
                    # Проверка лимита до генерации
                    try:
                        await check_ai_limit_only(redis, user_id, tokens_in)
                    except HTTPException as e:
                        if e.status_code == 429:
                            await websocket.send_json({"error": "Token limit exceeded"})
                            continue
                        else:
                            raise
                    # Генерация ответа
                    if needs_search and search_query:
                        answer = await process_web_search_results(search_query, text)
                        logger.info(f"Получен ответ на основе веб-поиска: {answer}")
                    else:
                        answer = await ActionAgent.handle_question(text)
                        logger.info(f"AI responded with default answer: {answer}")
                    # Инкремент входящих токенов
                    await increment_ai_limit(redis, user_id, tokens_in)
                    # Инкремент исходящих токенов
                    tokens_out = count_tokens(answer)
                    await increment_ai_limit(redis, user_id, tokens_out)
                    # --- синтез и отправка ответа (оставить как есть) ---

                    await check_voice_limit_only(redis, user_id, len(answer))

                    voice = os.getenv("ELEVEN_LABS_VOICE_ID")
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
                        tts_path = f.name
                    try:
                        await synthesize_speech_async(answer, voice, tts_path)
                    except NoAudioReceived:
                        answer = "Ошибка синтеза речи: не удалось получить аудио. Попробуйте другой язык или переформулируйте запрос."
                        logger.error("[TTS] No audio received from edge_tts.")
                        audio_b64 = ""
                    except Exception as tts_e:
                        logger.error(f"TTS error: {tts_e}", exc_info=True)
                        answer = f"Ошибка синтеза речи: {tts_e}"
                        audio_b64 = ""
                    else:
                        with open(tts_path, "rb") as f:
                            audio_b64 = base64.b64encode(f.read()).decode()
                        os.remove(tts_path)

                    await increment_voice_limit(redis, user_id, len(answer))

                    await websocket.send_json(
                        {"text": answer, "language": lang, "audio_base64": audio_b64}
                    )
                    logger.info(f"Sent TTS response for text: {answer}")
                    continue
                elif intent == "generate_text":
                    tokens_in = count_tokens(text)
                    try:
                        await check_ai_limit_only(redis, user_id, tokens_in)
                    except HTTPException as e:
                        if e.status_code == 429:
                            await websocket.send_json({"error": "Token limit exceeded"})
                            continue
                        else:
                            raise
                    result = await TextGenerationAgent.handle_generate_text(text, lang)
                    logger.info(f"AI generated text or note: {result}")
                    note_cmd = result.get("command", {})
                    answer = note_cmd.get("answer", "") if note_cmd else ""
                    # Инкремент входящих токенов
                    await increment_ai_limit(redis, user_id, tokens_in)
                    # Инкремент исходящих токенов
                    tokens_out = count_tokens(answer)
                    await increment_ai_limit(redis, user_id, tokens_out)
                    # --- синтез и отправка ответа (оставить как есть) ---

                    await check_voice_limit_only(redis, user_id, len(answer))

                    voice = os.getenv("ELEVEN_LABS_VOICE_ID")
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
                        tts_path = f.name
                    try:
                        await synthesize_speech_async(answer, voice, tts_path)
                    except Exception as tts_e:
                        logger.error(f"TTS error: {tts_e}", exc_info=True)
                        audio_b64 = ""
                    else:
                        with open(tts_path, "rb") as f:
                            audio_b64 = base64.b64encode(f.read()).decode()
                        os.remove(tts_path)
                    response_json = {
                        "answer": answer,
                        "audio_base64": audio_b64,
                        **result,
                    }

                    await increment_voice_limit(redis, user_id, len(answer))

                    logger.info(f"Sending generate_text response JSON: {response_json}")
                    await websocket.send_json(response_json)
                    logger.info("New note created with voice!!!")
                    continue

                elif intent == "calendar":
                    # Fetch user's events first
                    async with AsyncSessionLocal() as db:
                        events = await db.execute(
                            select(Event).where(Event.user_id == int(user_id))
                        )
                        user_events = [
                            {
                                "title": event.title,
                                "description": event.description,
                                "start_date": event.start_date,
                                "location": event.location,
                            }
                            for event in events.scalars().all()
                        ]

                        # Get AI response
                        cmd = await CalendarAgent.handle_calendar_command(
                            text, lang, user_events
                        )
                        logger.info(f"AI responded with calendar command: {cmd}")

                        # Handle event creation directly here
                        if cmd.get("command", {}).get("operation") == "create_event":
                            event_data = cmd["command"]["data"]
                            # Convert string date to datetime object
                            from datetime import datetime

                            start_date = datetime.fromisoformat(
                                event_data["start_date"]
                            )

                            new_event = Event(
                                title=event_data["title"],
                                description=event_data["description"],
                                start_date=start_date,  # Now it's a datetime object
                                location=event_data.get("location"),
                                user_id=int(user_id),
                            )
                            db.add(new_event)
                            await db.commit()

                            answer = cmd["command"]["answer"]
                            # Synthesize voice response
                            await check_voice_limit_only(redis, user_id, len(answer))

                            voice = os.getenv("ELEVEN_LABS_VOICE_ID")
                            with tempfile.NamedTemporaryFile(
                                delete=False, suffix=".mp3"
                            ) as f:
                                tts_path = f.name
                            try:
                                await synthesize_speech_async(answer, voice, tts_path)
                            except NoAudioReceived:
                                logger.error("[TTS] No audio received from edge_tts.")
                                audio_b64 = ""
                            except Exception as tts_e:
                                logger.error(f"TTS error: {tts_e}", exc_info=True)
                                audio_b64 = ""
                            else:
                                with open(tts_path, "rb") as f:
                                    audio_b64 = base64.b64encode(f.read()).decode()
                                os.remove(tts_path)

                            await increment_voice_limit(redis, user_id, len(answer))

                            # Send answer with audio
                            await websocket.send_json(
                                {"answer": answer, "audio_base64": audio_b64}
                            )
                        else:
                            # For queries, also add voice synthesis
                            answer = cmd["command"]["answer"]
                            await check_voice_limit_only(redis, user_id, len(answer))

                            voice = os.getenv("ELEVEN_LABS_VOICE_ID")
                            with tempfile.NamedTemporaryFile(
                                delete=False, suffix=".mp3"
                            ) as f:
                                tts_path = f.name
                            try:
                                await synthesize_speech_async(answer, voice, tts_path)
                            except NoAudioReceived:
                                logger.error("[TTS] No audio received from edge_tts.")
                                audio_b64 = ""
                            except Exception as tts_e:
                                logger.error(f"TTS error: {tts_e}", exc_info=True)
                                audio_b64 = ""
                            else:
                                with open(tts_path, "rb") as f:
                                    audio_b64 = base64.b64encode(f.read()).decode()
                                os.remove(tts_path)

                            await increment_voice_limit(redis, user_id, len(answer))

                            # Send full command with audio
                            cmd["audio_base64"] = audio_b64
                            await websocket.send_json(cmd)
                        continue
                else:
                    answer = "Please, repeat your command."
                    logger.info("AI could not understand request")

                voice = os.getenv("ELEVEN_LABS_VOICE_ID")
                with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
                    tts_path = f.name
                try:
                    await synthesize_speech_async(answer, voice, tts_path)
                except NoAudioReceived:
                    answer = "Ошибка синтеза речи: не удалось получить аудио. Попробуйте другой язык или переформулируйте запрос."
                    logger.error("[TTS] No audio received from edge_tts.")
                    audio_b64 = ""
                except Exception as tts_e:
                    logger.error(f"TTS error: {tts_e}", exc_info=True)
                    answer = f"Ошибка синтеза речи: {tts_e}"
                    audio_b64 = ""
                else:
                    with open(tts_path, "rb") as f:
                        audio_b64 = base64.b64encode(f.read()).decode()
                    os.remove(tts_path)

                await websocket.send_json(
                    {"text": answer, "language": lang, "audio_base64": audio_b64}
                )
                logger.info(f"Sent TTS response for text: {answer}")

            elif "text" in msg:
                try:
                    parsed = json.loads(msg["text"])
                    if isinstance(parsed, dict) and "tabs" in parsed:
                        user_tabs = parsed["tabs"]
                        logger.info(f"Received user tabs: {user_tabs}")
                except json.JSONDecodeError:
                    logger.error("Failed to decode JSON from text message.")

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected by client.")
        pass
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
        try:
            await websocket.close(code=1011, reason="Server error")
        except:
            logger.error("Failed to close websocket after error.")


async def handle_web_search(query: str):
    url = "https://google.serper.dev/search"

    payload = json.dumps({"q": query})

    headers = {
        "X-API-KEY": os.getenv("SERPER_API_KEY"),
        "Content-Type": "application/json",
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, data=payload) as response:
            return await response.json()
