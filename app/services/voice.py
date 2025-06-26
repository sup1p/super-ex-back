import re
import json
import edge_tts
import whisper
import httpx
import logging
import os


CMD_JSON_RE = re.compile(r"\{.*\}", re.S)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"


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
        - command (browser/tab actions)
        - question
        - media (play, pause, next, previous, etc. for video/audio)
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
        User: "какая погода?" → question
        User: "спасибо" → noise

        Input: \"{text}\"
        """
        print(f"[IntentAgent] Input: {text}")
        print(f"[IntentAgent] Prompt: {prompt}")
        response = await get_ai_answer(prompt)
        print(f"[IntentAgent] Output: {response}")
        return response.strip().lower()


class ActionAgent:
    @staticmethod
    async def handle_command(
        text: str, lang: str, tabs: list[dict], confidence: float
    ) -> dict:
        prompt = build_prompt(text, confidence, lang, tabs)
        print(
            f"[ActionAgent] Input: {text}, lang: {lang}, confidence: {confidence}, tabs: {tabs}"
        )
        print(f"[ActionAgent] Prompt: {prompt}")
        response = await get_ai_answer(prompt)
        print(f"[ActionAgent] Output: {response}")
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
        print(f"[ActionAgent] Input (question): {text}, lang: {lang}")
        print(f"[ActionAgent] Prompt (question): {prompt}")
        response = await get_ai_answer(prompt)
        print(f"[ActionAgent] Output (question): {response}")
        return response


def build_prompt(user_text: str, confidence: float, lang: str, tabs: list[dict]) -> str:
    tabs_description_parts = []
    for tab in tabs:
        active_status = " (active)" if tab.get("active") else ""
        tabs_description_parts.append(
            f"- Tab {tab['index']}: {tab['url']}{active_status}"
        )
    tabs_description = "\\n".join(tabs_description_parts)

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

        2. Close a single tab by keyword or index:
        {{ "action": "close_tab", "tabIndex": 5 }}
        
        3. Close multiple tabs by keywords or rules:
        {{ "action": "close_tab", "tabIndices": [0, 1, 4] }}

        4. Open a new website:
        {{ "action": "open_url", "url": "https://youtube.com" }}


        RULES:
        - For "switch_tab" or "close_tab" (single), find the tab that best matches the user's keywords (e.g., "YouTube", "чатжпт") in the URL and return its index.
        - For "close_tab" with multiple tabs:
          - If the user says "close all tabs except the active one", find all tab indices that are not active and return them in the "tabIndices" array.
          - If the user names multiple tabs (e.g., "close extensions and localhost"), find the indices for all matching tabs and return them.
        - For "open_url", if no matching tab is found and the user wants to open a new site, return the appropriate full URL.
        - If uncertain what to do — respond:
        {{ "action": "noop" }}
        
        If confidence < 0.85 or user input is unclear — respond in user language: "Please repeat your command".

        - JSON must be strict and in English only. DO NOT add any text or comments outside the JSON.

        USER INPUT:
        "{user_text}"
        """
    return rules.strip()


async def synthesize_speech_async(answer, voice, tts_path):
    communicate = edge_tts.Communicate(answer, voice=voice)
    await communicate.save(tts_path)


_model = None


def get_whisper_model():
    global _model
    if _model is None:
        _model = whisper.load_model("small")  # можно добавить device="cpu"
    return _model


async def transcribe_audio_async(audio_path):
    model = get_whisper_model()
    return model.transcribe(
        audio_path,
        no_speech_threshold=0.8,
        temperature=0.0,
    )


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
        print(f"[MediaAgent] Input: {text}, lang: {lang}")
        print(f"[MediaAgent] Prompt: {prompt}")
        response = await get_ai_answer(prompt)
        print(f"[MediaAgent] Output: {response}")
        match = CMD_JSON_RE.search(response)
        if match:
            json_str = match.group(0)
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                return {"command": {"action": "control_media", "mediaCommand": "noop"}}
        return {"command": {"action": "control_media", "mediaCommand": "noop"}}
