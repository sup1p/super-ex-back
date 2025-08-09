from fastapi import WebSocket, HTTPException, WebSocketDisconnect
from sqlalchemy import select
from edge_tts.exceptions import NoAudioReceived


from app.core.dependencies.utils import is_valid_text, count_tokens

from app.token_limit import (
    check_ai_limit_only,
    check_voice_limit_only,
    increment_voice_limit,
    increment_ai_limit,
)

from app.core.dependencies.web import voice_website_summary

import app.redis_client
from app.core.database import get_db
from app.core.config import settings
from app.models import Event

from app.services.voice.speech import synthesize_speech_async, transcribe_audio_async
from app.services.voice.web_search import needs_web_search, process_web_search_results

from app.services.voice.agents.intent_agent import IntentAgent
from app.services.voice.agents.action_agent import ActionAgent
from app.services.voice.agents.media_agent import MediaAgent
from app.services.voice.agents.text_gen_agent import TextGenerationAgent
from app.services.voice.agents.calendar_agent import CalendarAgent


import os
import logging
import tempfile
import base64
import json
import re


voice = settings.eleven_labs_voice_id

CMD_JSON_RE = re.compile(r"^\s*\{.*\}\s*$", re.S)  # грубая проверка JSON


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
                    async with get_db() as db:
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
                                reminder=15,
                            )
                            db.add(new_event)
                            await db.commit()
                            logger.info(f"New event created: {new_event}")

                            answer = cmd["command"]["answer"]
                            # Synthesize voice response
                            await check_voice_limit_only(redis, user_id, len(answer))

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
