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


class IntentAgent:
    @staticmethod
    async def detect_intent(text: str) -> str:
        prompt = f"""
        Classify the user's intent into one of the following:
        - command
        - question
        - noise
        - uncertain

        Respond with ONLY one word.
        Input: "{text}"
        """
        response = await get_ai_answer(prompt)
        return response.strip().lower()


class ActionAgent:
    @staticmethod
    async def handle_command(
        text: str, lang: str, tabs: list[dict], confidence: float
    ) -> dict:
        prompt = build_prompt(text, confidence, lang, tabs)
        print(f"AI received tex with language: {lang}")
        response = await get_ai_answer(prompt)
        print(f"AI responded with: {response}")
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
        return await get_ai_answer(prompt)


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
