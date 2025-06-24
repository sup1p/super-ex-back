from fastapi import Depends, HTTPException, status, WebSocket, WebSocketDisconnect
from jose import jwt, JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models import User
import httpx
import os
from dotenv import load_dotenv
import logging
import re
import traceback
import tempfile
import whisper
import base64
import edge_tts

load_dotenv()

voice_map = {
    "ru": "ru-RU-DmitryNeural",
    "en": "en-US-GuyNeural",
    "de": "de-DE-ConradNeural",
    "fr": "fr-FR-HenriNeural",
    "es": "es-ES-AlvaroNeural",
    "kk": "kk-KZ-DauletNeural",
}

model = whisper.load_model("small")


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


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"


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


async def get_ai_answer(question: str):
    logging.info(f"get_ai_answer: {question}")
    payload = {"contents": [{"role": "user", "parts": [{"text": question}]}]}
    headers = {"Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(GEMINI_URL, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            try:
                text_answer = data["candidates"][0]["content"]["parts"][0]["text"]
            except (KeyError, IndexError):
                text_answer = "Что-то пошло не так"
            clean_text = text_answer.replace("\n", "").strip()
            return clean_text
    except httpx.ReadTimeout:
        logging.error("get_ai_answer: ReadTimeout")
        return "Внешний сервис не ответил вовремя (таймаут). Попробуйте позже."
    except Exception as e:
        logging.error(f"get_ai_answer: Ошибка обращения к ИИ: {e}")
        return f"Ошибка обращения к ИИ: {e}"


import json, os, re, tempfile, traceback
from fastapi import WebSocket, WebSocketDisconnect

# --- вспомогательные функции -------------------------------------------------

CMD_JSON_RE = re.compile(r"^\s*\{.*\}\s*$", re.S)  # грубая проверка JSON


def build_prompt(user_text: str, confidence: float, lang: str, tabs: list[dict]) -> str:
    tabs_description = "\n".join(
        [f"- Tab {tab['index']}: {tab['url']}" for tab in tabs]
    )

    rules = f"""
        You are a multilingual voice assistant in a browser extension.
        User speaks: {lang}
        Transcription confidence: {confidence:.2f}

        --- USER BROWSER TABS ---
        {tabs_description if tabs else "No tabs are currently open."}

        --- TASK ---
        Analyze the user's input and determine whether it is a browser command.

        If it is a command, respond ONLY with a valid JSON object that matches one of the following formats:
        1. Switch to an existing tab by keyword:
        {{ "action": "switch_tab", "tabIndex": 2 }}

        2. Close a tab by keyword or index:
        {{ "action": "close_tab", "tabIndex": 5 }}

        3. Open a new website:
        {{ "action": "open_url", "url": "https://youtube.com" }}


        RULES:
        - Always match keywords (e.g. "YouTube", "чатжпт") to open tab URLs.
        - If user says something like "перейди на ютуб", find a matching tab (e.g. one containing "youtube.com") and return its tabId.
        - If no match is found and user wants to open a new site — return appropriate full URL (you decide).
        - If uncertain what to do — respond:
        {{ "action": "noop" }}
        - If you could not identify the command answer as default
        
        If confidence < 0.85 or user input is unclear — respond in user language: "Please repeat your command".

        - JSON must be strict and in English only. DO NOT add any text or comments outside the JSON.
        - DO NOT Write Json before the json itself

        USER INPUT:
        "{user_text}"
        """
    return rules.strip()


# --- основная точка входа -----------------------------------------------------


async def handle_voice_websocket(websocket: WebSocket):
    await websocket.accept()
    print("WebSocket соединение установлено")

    last_text = ""
    user_tabs = []

    try:
        while True:
            msg = await websocket.receive()

            if "bytes" in msg:
                audio_bytes = msg["bytes"]

                if not audio_bytes:
                    continue

                with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as f:
                    f.write(audio_bytes)
                    audio_path = f.name

                try:
                    # Транскрипция
                    result = model.transcribe(
                        audio_path,
                        no_speech_threshold=0.8,
                        temperature=0.0,
                    )
                    os.remove(audio_path)

                    text = result.get("text", "").strip()
                    if not is_valid_text(text) or text == last_text:
                        print(f"Пропущен текст: {text}")
                        continue
                    last_text = text

                    avg_logprob = result.get("avg_logprob", -1.0)
                    no_speech_p = result.get("no_speech_prob", 1.0)
                    lang = result.get("language", "en")
                    confidence = 1 - max(no_speech_p, -avg_logprob)

                    # Построение prompt с учётом вкладок
                    prompt = build_prompt(text, confidence, lang, user_tabs)
                    ai_answer = await get_ai_answer(prompt)

                    if CMD_JSON_RE.match(ai_answer):
                        try:
                            cmd = json.loads(ai_answer)
                            print(f"Gemini вернул команду: {cmd}")
                            await websocket.send_json({"command": cmd})
                            continue
                        except json.JSONDecodeError:
                            print("Ошибка JSON, возвращаем обычный ответ")

                    # Озвучивание текста
                    voice = voice_map.get(lang, "en-US-GuyNeural")
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
                        tts_path = f.name

                    communicate = edge_tts.Communicate(ai_answer, voice=voice)
                    await communicate.save(tts_path)

                    with open(tts_path, "rb") as f:
                        audio_b64 = base64.b64encode(f.read()).decode()
                    os.remove(tts_path)

                    await websocket.send_json(
                        {"text": ai_answer, "language": lang, "audio_base64": audio_b64}
                    )
                    print("Ответ TTS отправлен")

                except Exception:
                    traceback.print_exc()
                    await websocket.send_json(
                        {
                            "text": "Ошибка обработки аудио",
                            "language": "ru",
                            "audio_base64": "",
                        }
                    )

            elif "text" in msg:
                try:
                    parsed = json.loads(msg["text"])
                    if isinstance(parsed, dict) and "tabs" in parsed:
                        user_tabs = parsed["tabs"]
                        print(f"Обновлены вкладки пользователя: {len(user_tabs)} шт.")
                except json.JSONDecodeError:
                    print("Ошибка разбора текста: невалидный JSON")

    except WebSocketDisconnect:
        print("Клиент отключился")
    except Exception:
        traceback.print_exc()
        try:
            await websocket.close(code=1011, reason="Server error")
        except:
            pass
