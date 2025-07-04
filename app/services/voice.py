import re
import json
import aiohttp
import httpx
import os
from faster_whisper import WhisperModel
import logging

CMD_JSON_RE = re.compile(r"\{.*\}", re.S)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_DEPLOYMENT_NAME = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")


logger = logging.getLogger(__name__)

"""
Server Response Format for Media Control Commands
------------------------------------------------
The server must return an object with a 'command' field containing:
    action: string, always "control_media" (or "control_video" for backward compatibility)
    mediaCommand: string, the media action (e.g., "play", "pause", "next", "prev", "forward", "backward", "toggle")

Example response:
{
  "command": {
    "action": "control_media",
    "mediaCommand": "next"
  }
}

Possible values for mediaCommand:
- "play"      — play video/audio
- "pause"     — pause video/audio
- "toggle"    — toggle play/pause
- "next"      — next video (if multiple on page)
- "prev"      — previous video
- "forward"   — seek forward (e.g., 20 seconds)
- "backward"  — seek backward (e.g., 20 seconds)
- "volume_up" — increase volume
- "volume_down" — decrease volume
"""


class IntentAgent:
    @staticmethod
    async def detect_intent(text: str) -> str:
        prompt = f"""
        Classify the user's intent into one of the following:
        - command (browser/tab actions like open, close, switch, or **searching** on Google/YouTube)
        - question
        - media (controlling media **on the current page**: play, pause, next, volume)
        - generate_text (user wants to generate an essay, summary, article, note, etc.)
        - noise
        - uncertain

        Respond with ONLY one word.

        Examples:
        User: "поставь видео на паузу" → media
        User: "play the video" → media
        User: "pause music" → media
        User: "сделай погромче" → media
        User: "следующее видео" → media
        User: "открой ютуб" → command
        User: "закрой вкладку" → command
        User: "найди видео с котиками" → command
        User: "включи видео про dota 2" → commandimport aiohttp

        User: "search for how to cook pasta" → command
        User: "какая погода?" → question
        User: "Какие новости в Казахстане?" → question
        User: "Что делать если сломал ногу?" → question
        User: "спасибо" → noise
        User: "Напиши эссе о космосе" → generate_text
        User: "Сделай реферат по истории" → generate_text
        User: "Создай заметку: купить хлеб" → generate_text
        User: "Запиши: позвонить маме завтра" → generate_text

        Input: \"{text}\"
        """
        response = await get_35_ai_answer(prompt)
        return response.strip().lower()


class ActionAgent:
    @staticmethod
    async def handle_command(text: str, lang: str, tabs: list[dict]) -> dict:
        prompt = build_prompt(text, lang, tabs)
        response = await get_35_ai_answer(prompt)
        match = CMD_JSON_RE.search(response)
        if match:
            json_str = match.group(0)
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                return {"action": "noop"}
        return {"action": "noop"}

    @staticmethod
    async def handle_question(text: str, lang: str) -> str:
        prompt = f"""
        Respond to the following user question in the same language it was asked.
        - Limit your response to no more than 35 words.
        - Do not use asterisks (*) or markdown symbols.

        Question:
        {text}
        """
        response = await get_35_ai_answer(prompt)
        return response


def build_prompt(user_text: str, lang: str, tabs: list[dict]) -> str:
    tabs_description_parts = []
    for tab in tabs:
        active_status = " (active)" if tab.get("active") else ""
        tabs_description_parts.append(
            f"- Tab {tab['index']}: {tab['url']}{active_status}"
        )
    tabs_description = "\n".join(tabs_description_parts)

    rules = f"""
        You are a multilingual voice assistant in a browser extension.
        User speaks: {lang}

        --- USER BROWSER TABS ---
        {tabs_description if tabs else "No tabs are currently open."}

        --- TASK ---
        Analyze the user's input and determine whether it is a browser command.

        If it is a command, respond ONLY with a valid JSON object that matches one of the following formats:
        1. Switch to an existing tab by keyword:
        {{ "action": "switch_tab", "tabIndex": 2 }}

        2. Close a single tab by keyword or index:
        {{ "action": "close_tab", "tabIndex": 5 }}
        
        3. Close multiple tabs by keywords or rules:
        {{ "action": "close_tab", "tabIndices": [0, 1, 4] }}

        4. Open a new website:
        {{ "action": "open_url", "url": "https://youtube.com" }}

        5. Search on the web (e.g., Google, YouTube):
        {{ "action": "open_url", "url": "https://www.google.com/search?q=some+search+query" }}

        RULES:
        - For "switch_tab" or "close_tab" (single), find the tab that best matches the user's keywords (e.g., "YouTube", "чатжпт") in the URL and return its index.
        - For "close_tab" with multiple tabs:
          - If the user says "close all tabs except the active one", find all tab indices that are not active and return them in the "tabIndices" array.
          - If the user names multiple tabs (e.g., "close extensions and localhost"), find the indices for all matching tabs and return them.
        - For "open_url", if the user provides a direct URL or a site name, use that.
        - If the user asks to find something (e.g., "find cats" or "search for music on YouTube"), construct a search URL and use the "open_url" action. Default to Google search unless another service like YouTube is specified.
        - If uncertain what to do — respond:
        {{ "action": "noop" }}
        
        EXAMPLES:
        - User input: "включи видео с котятами на ютуб" -> {{ "action": "open_url", "url": "https://www.youtube.com/results?search_query=видео+с+котятами" }}
        - User input: "найди рецепт борща" -> {{ "action": "open_url", "url": "https://www.google.com/search?q=рецепт+борща" }}
        
        If user input is unclear — respond in user language: "Please repeat your command".

        - JSON must be strict and in English only. DO NOT add any text or comments outside the JSON.

        --- ОТЧЕТ ДЛЯ ПОЛЬЗОВАТЕЛЯ ---
        In addition to the required fields, ALWAYS add a field "answer" (in the same JSON), where you briefly and clearly report to the user in their language what you did (for example: 'Я открыла сайт: youtube.com', 'Я закрыла вкладку 2', etc.).

        USER INPUT:
        "{user_text}"
        """
    return rules.strip()


ELEVEN_LABS_API_KEY = os.getenv("ELEVEN_LABS_API_KEY")


async def synthesize_speech_async(text: str, voice_id: str, output_path: str):
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": ELEVEN_LABS_API_KEY,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    payload = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.7},
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers) as resp:
            if resp.status != 200:
                raise Exception(f"TTS failed: {resp.status} - {await resp.text()}")
            with open(output_path, "wb") as f:
                f.write(await resp.read())


_model = None


def get_whisper_model():
    global _model
    if _model is None:
        _model = WhisperModel("small", compute_type="int8", device="cpu")
    return _model


async def transcribe_audio_async(audio_path):
    model = get_whisper_model()
    segments, info = model.transcribe(audio_path, beam_size=1)
    full_text = "".join(segment.text for segment in segments).strip()

    logger.info(f"Transcription result: {full_text}")

    return {
        "text": full_text,
        "language": info.language,
    }


async def get_ai_answer(question: str):
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
        return "Внешний сервис не ответил вовремя (таймаут). Попробуйте позже."
    except Exception as e:
        return f"Ошибка обращения к ИИ: {e}"


async def get_35_ai_answer(question: str):
    url = f"{AZURE_OPENAI_ENDPOINT}"
    headers = {
        "Content-Type": "application/json",
        "api-key": AZURE_OPENAI_KEY,
    }
    payload = {
        "messages": [
            {"role": "system", "content": "Ты полезный ассистент."},
            {"role": "user", "content": question},
        ],
        "temperature": 0.7,
        "max_tokens": 1000,
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()
    except httpx.ReadTimeout:
        return "Сервер GPT-3.5 не ответил вовремя (таймаут)."
    except Exception as e:
        logger.error(f"Ошибка обращения к GPT-3.5: {e}")
        return


class MediaAgent:
    MEDIA_COMMANDS = [
        "play",
        "pause",
        "toggle",
        "next",
        "prev",
        "forward",
        "backward",
        "volume_up",
        "volume_down",
    ]

    @staticmethod
    async def handle_media_command(text: str, lang: str) -> dict:
        """
        Analyze user input and map it to a media command.
        Returns a dict in the required format for media control.
        """
        prompt = f"""
You are a multilingual assistant for browser media control. The user may speak in any language and use various ways to express their intent.

Your task: Analyze the user's request and map it to one of these media commands:
- play
- pause
- toggle
- next
- prev
- forward
- backward
- volume_up
- volume_down

Respond ONLY with a JSON object in this format:
{{
  \"command\": {{
    \"action\": \"control_media\",
    \"mediaCommand\": \"<one of: play, pause, toggle, next, prev, forward, backward, volume_up, volume_down>\"
  }}
}}

Do not add any text or comments outside the JSON.

You must understand the user's intent even if the command is formulated in an unusual way, in any language, or with synonyms. Use your best judgment to match the intent to the closest media command.

Examples:
User: "Сделай погромче" → {{"command": {{"action": "control_media", "mediaCommand": "volume_up"}}}}
User: "Volume up" → {{"command": {{"action": "control_media", "mediaCommand": "volume_up"}}}}
User: "Сделай потише" → {{"command": {{"action": "control_media", "mediaCommand": "volume_down"}}}}
User: "Volume down" → {{"command": {{"action": "control_media", "mediaCommand": "volume_down"}}}}
User: "Поставь видео на паузу" → {{"command": {{"action": "control_media", "mediaCommand": "pause"}}}}
User: "Останови видео" → {{"command": {{"action": "control_media", "mediaCommand": "pause"}}}}
User: "Pause the video." → {{"command": {{"action": "control_media", "mediaCommand": "pause"}}}}
User: "Pause o vídeo." → {{"command": {{"action": "control_media", "mediaCommand": "pause"}}}}
User: "Deixa o vídeo parado." → {{"command": {{"action": "control_media", "mediaCommand": "pause"}}}}
User: "Play the next video" → {{"command": {{"action": "control_media", "mediaCommand": "next"}}}}
User: "Следующее видео" → {{"command": {{"action": "control_media", "mediaCommand": "next"}}}}
User: "Avançar vídeo" → {{"command": {{"action": "control_media", "mediaCommand": "forward"}}}}
User: "Перемотай вперед" → {{"command": {{"action": "control_media", "mediaCommand": "forward"}}}}
User: "Назад на 20 секунд" → {{"command": {{"action": "control_media", "mediaCommand": "backward"}}}}
User: "Toggle a video" → {{"command": {{"action": "control_media", "mediaCommand": "toggle"}}}}
User: "Включить видео" → {{"command": {{"action": "control_media", "mediaCommand": "play"}}}}
User: "Start the video" → {{"command": {{"action": "control_media", "mediaCommand": "play"}}}}
User: "Resume playback" → {{"command": {{"action": "control_media", "mediaCommand": "play"}}}}
User: "Pause" → {{"command": {{"action": "control_media", "mediaCommand": "pause"}}}}
User: "Stop" → {{"command": {{"action": "control_media", "mediaCommand": "pause"}}}}

If the request is unclear or not related to media, respond:
{{"command": {{"action": "control_media", "mediaCommand": "noop"}}}}

User language: {lang}
User input: "{text}"
"""
        response = await get_35_ai_answer(prompt)
        match = CMD_JSON_RE.search(response)
        if match:
            json_str = match.group(0)
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                return {"command": {"action": "control_media", "mediaCommand": "noop"}}
        return {"command": {"action": "control_media", "mediaCommand": "noop"}}


class TextGenerationAgent:
    @staticmethod
    async def handle_generate_text(text: str, lang: str) -> dict:
        prompt = f"""
        Analyze the user's request. If the user asks to create a note, essay, story, article, summary, letter, or any other type of text — complete the task and ALWAYS return the RESPONSE ONLY as a strict JSON in the following format:
        {{
          "command": {{
            "action": "create_note",
            "title": "<short title or topic, 2-3 words>",
            "text": "<main text, full response>",
            "answer": "<short report for the user in their language, e.g. 'Я создала заметку: Покормить кота'>"
          }}
        }}

        Rules:
        - If it is a note, action = create_note, title — a short summary of the note, text — the full note text.
        - If the user did not provide an explicit title, invent a short title based on the meaning.
        - Do not add any comments, explanations, or text outside the JSON.
        - Always return only JSON in the specified format.
        - The response language must match the user's language.
        - ALWAYS add a field "answer" (in the same JSON), where you briefly and clearly report to the user in their language what you did (for example: 'Я создала заметку: Покормить кота').

        Examples:
        User: "Create a note: buy bread and milk" → {{"command": {{"action": "create_note", "title": "Shopping List", "text": "Buy bread and milk", "answer": "Я создала заметку: Список покупок"}}}}
        User: "Write an essay about space" → {{"command": {{"action": "create_note", "title": "Space", "text": "<essay about space>", "answer": "Я создала заметку: Космос"}}}}
        User: "Make a summary on Russian history" → {{"command": {{"action": "create_note", "title": "Russian History", "text": "<summary>", "answer": "Я создала заметку: История России"}}}}
        User: "Create a story about a cat" → {{"command": {{"action": "create_note", "title": "Cat Story", "text": "<story>", "answer": "Я создала заметку: История кота"}}}}
        User: "Note: call mom tomorrow" → {{"command": {{"action": "create_note", "title": "Call Mom", "text": "Call mom tomorrow", "answer": "Я создала заметку: Позвонить маме"}}}}

        User language: {lang}
        User request: "{text}"
        """
        response = await get_ai_answer(prompt)
        # Try to parse as note command, otherwise return as plain text
        match = CMD_JSON_RE.search(response)
        if match:
            json_str = match.group(0)
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                pass
        return {"text": response}
