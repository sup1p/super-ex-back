import re
import json
import aiohttp
import httpx
import os
from faster_whisper import WhisperModel
import logging
import asyncio

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
        User: "включи видео про dota 2" → command

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
    async def handle_question(text: str) -> str:
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
        ВАЖНО: Ты должен понимать команды на ЛЮБОМ языке, включая смешанные языки, сленг, синонимы, сокращения, опечатки, а также любые нестандартные формулировки. Не ограничивайся только примерами — анализируй СМЫСЛ сказанного, даже если слова отличаются. Если команда выражена необычно, но смысл ясен — выполняй её максимально точно.

        You are a multilingual voice assistant in a browser extension.
        User speaks: {lang}

        --- USER BROWSER TABS ---
        {tabs_description if tabs else "No tabs are currently open."}

        --- TASK ---
        Analyze the user's input and determine whether it is a browser command.
        Понимай смысл, а не только слова. Пользователь может использовать любые формулировки, синонимы, сокращения, опечатки, сленг, микс языков — твоя задача понять, что он хочет, даже если это не похоже на примеры.

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
        - For "switch_tab" or "close_tab" (single), find the tab that best matches the user's keywords (e.g., "YouTube", "чатжпт") in the URL and return its index. Используй синонимы, перефразировки, догадайся по смыслу.
        - For "close_tab" with multiple tabs:
          - If the user says "close all tabs except the active one", find all tab indices that are not active and return them in the "tabIndices" array.
          - If the user names multiple tabs (e.g., "close extensions and localhost"), find the indices for all matching tabs and return them.
        - For "open_url", if the user provides a direct URL or a site name, use that.
        - If the user asks to find something (e.g., "find cats" or "search for music on YouTube"), construct a search URL and use the "open_url" action. Default to Google search unless another service like YouTube is specified.
        - If uncertain what to do — сначала попробуй догадаться по смыслу, только если совсем неясно — respond:
        {{ "action": "noop" }}
        
        EXAMPLES:
        - User input: "включи(или открой, или найди, или покажи) видео с котятами на ютуб" -> {{ "action": "open_url", "url": "https://www.youtube.com/results?search_query=видео+с+котятами" }}
        - User input: "найди рецепт борща" -> {{ "action": "open_url", "url": "https://www.google.com/search?q=рецепт+борща" }}
        - User input: "открой сайт с котиками" -> {{ "action": "open_url", "url": "https://www.google.com/search?q=сайт+с+котиками" }}
        - User input: "закрой все вкладки кроме первой" -> {{ "action": "close_tab", "tabIndices": [1,2,3] }}
        - User input: "переключись на вкладку с музыкой" -> {{ "action": "switch_tab", "tabIndex": 4 }}
        
        Examples are just examples, user can say whatever they want, but the meaning can remain the same! Ты должен понимать даже если формулировка совсем другая.
        
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
    # Retry configuration
    max_retries = 3
    base_delay = 1.0  # seconds

    for attempt in range(max_retries):
        try:
            # Create a new client for each attempt to avoid connection issues
            async with httpx.AsyncClient(
                timeout=15,
                limits=httpx.Limits(max_keepalive_connections=1, max_connections=1),
                http2=False,  # Disable HTTP/2 to avoid potential issues
            ) as client:
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
            logger.warning(f"Gemini timeout on attempt {attempt + 1}/{max_retries}")
            if attempt == max_retries - 1:
                return "Внешний сервис не ответил вовремя (таймаут). Попробуйте позже."
            await asyncio.sleep(base_delay * (2**attempt))  # Exponential backoff

        except httpx.ConnectError as e:
            logger.warning(
                f"Gemini connection error on attempt {attempt + 1}/{max_retries}: {e}"
            )
            if attempt == max_retries - 1:
                return "Ошибка подключения к сервису ИИ. Проверьте интернет-соединение."
            await asyncio.sleep(base_delay * (2**attempt))

        except httpx.HTTPStatusError as e:
            logger.error(
                f"Gemini HTTP error on attempt {attempt + 1}/{max_retries}: {e.response.status_code}"
            )
            if attempt == max_retries - 1:
                return f"Ошибка сервера ИИ (код {e.response.status_code}). Попробуйте позже."
            await asyncio.sleep(base_delay * (2**attempt))

        except Exception as e:
            logger.error(
                f"Gemini unexpected error on attempt {attempt + 1}/{max_retries}: {e}"
            )
            if attempt == max_retries - 1:
                return f"Ошибка обращения к ИИ: {e}"
            await asyncio.sleep(base_delay * (2**attempt))

    return "Ошибка обращения к ИИ. Попробуйте позже."


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

    # Retry configuration
    max_retries = 3
    base_delay = 1.0  # seconds

    for attempt in range(max_retries):
        try:
            # Create a new client for each attempt to avoid connection issues
            async with httpx.AsyncClient(
                timeout=15,
                limits=httpx.Limits(max_keepalive_connections=1, max_connections=1),
                http2=False,  # Disable HTTP/2 to avoid potential issues
            ) as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"].strip()

        except httpx.ReadTimeout:
            logger.warning(f"GPT-3.5 timeout on attempt {attempt + 1}/{max_retries}")
            if attempt == max_retries - 1:
                return "Сервер GPT-3.5 не ответил вовремя (таймаут)."
            await asyncio.sleep(base_delay * (2**attempt))  # Exponential backoff

        except httpx.ConnectError as e:
            logger.warning(
                f"GPT-3.5 connection error on attempt {attempt + 1}/{max_retries}: {e}"
            )
            if attempt == max_retries - 1:
                return "Ошибка подключения к сервису ИИ. Проверьте интернет-соединение."
            await asyncio.sleep(base_delay * (2**attempt))

        except httpx.HTTPStatusError as e:
            logger.error(
                f"GPT-3.5 HTTP error on attempt {attempt + 1}/{max_retries}: {e.response.status_code}"
            )
            if attempt == max_retries - 1:
                return f"Ошибка сервера ИИ (код {e.response.status_code}). Попробуйте позже."
            await asyncio.sleep(base_delay * (2**attempt))

        except Exception as e:
            logger.error(
                f"GPT-3.5 unexpected error on attempt {attempt + 1}/{max_retries}: {e}"
            )
            if attempt == max_retries - 1:
                return "Ошибка подключения к сервису ИИ. Попробуйте позже."
            await asyncio.sleep(base_delay * (2**attempt))

    return "Ошибка подключения к сервису ИИ. Попробуйте позже."


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


async def needs_web_search(text: str) -> tuple[bool, str]:
    """
    Определяет, нужен ли веб-поиск для ответа на вопрос пользователя.
    Возвращает (нужен_ли_поиск, поисковый_запрос)
    """
    prompt = f"""
    Проанализируй вопрос пользователя и определи, нужен ли веб-поиск для получения актуальной информации.
    
    ВЕБ-ПОИСК НУЖЕН для:
    - Погоды (текущая погода, прогноз)
    - Новостей (актуальные события, последние новости)
    - Курсов валют (текущие курсы)
    - Цен на товары/услуги
    - Информации о событиях, концертах, фильмах
    - Статистики (спорт, экономика, политика)
    - Любой информации, которая может измениться со временем
    
    ВЕБ-ПОИСК НЕ НУЖЕН для:
    - Общих знаний (история, наука, факты)
    - Объяснений понятий
    - Советов и рекомендаций общего характера
    - Математических расчетов
    - Личных вопросов
    
    Ответь в формате JSON:
    {{
        "needs_search": true/false,
        "search_query": "поисковый запрос на русском языке"
    }}
    
    Если поиск не нужен, search_query может быть пустым.
    
    Примеры:
    "Какая погода в Москве?" → {{"needs_search": true, "search_query": "погода Москва сегодня"}}
    "Кто такой Пушкин?" → {{"needs_search": false, "search_query": ""}}
    "Какие новости в Казахстане?" → {{"needs_search": true, "search_query": "новости Казахстан сегодня"}}
    "Как приготовить борщ?" → {{"needs_search": false, "search_query": ""}}
    "Курс доллара к рублю" → {{"needs_search": true, "search_query": "курс доллара к рублю сегодня"}}
    
    Вопрос: "{text}"
    """

    try:
        response = await get_ai_answer(prompt)
        # Ищем JSON в ответе
        import json
        import re

        json_match = re.search(r"\{.*\}", response, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            return result.get("needs_search", False), result.get("search_query", "")
        else:
            # Если JSON не найден, попробуем определить по ключевым словам
            search_keywords = [
                "погода",
                "weather",
                "новости",
                "news",
                "курс",
                "курс валют",
                "цена",
                "price",
                "стоимость",
                "расписание",
                "schedule",
                "сегодня",
                "today",
                "сейчас",
                "now",
                "актуальн",
                "current",
            ]
            text_lower = text.lower()
            needs_search = any(keyword in text_lower for keyword in search_keywords)
            return needs_search, text if needs_search else ""
    except Exception as e:
        logger.error(f"Ошибка при определении необходимости поиска: {e}")
        return False, ""


async def process_web_search_results(search_query: str, original_question: str) -> str:
    """
    Processes web search results and generates an answer based on the found information.
    The answer will be in the same language as the original question, determined automatically.
    """
    try:
        from app.core.dependencies import handle_web_search
        import json
        import re

        # Language detection utility (simple heuristic, can be replaced with a library)
        def detect_language(text):
            try:
                import langdetect

                return langdetect.detect(text)
            except ImportError:
                # Fallback: simple heuristic for English/Russian
                cyrillic = re.compile("[\u0400-\u04ff]")
                if cyrillic.search(text):
                    return "ru"
                return "en"

        user_lang = detect_language(original_question)

        # Perform the search
        search_data = await handle_web_search(search_query)

        # Check if we got data
        if not search_data or "organic" not in search_data:
            return f"Could not find any information for request: '{search_query}'."

        # Extract the most relevant results
        organic_results = search_data.get("organic", [])
        if not organic_results:
            return f"Could not find any information for request: '{search_query}'."

        # Take the top 3 results for analysis
        top_results = organic_results[:3]

        # Summarize the results for the AI
        results_summary = []
        for i, result in enumerate(top_results, 1):
            title = result.get("title", "")
            snippet = result.get("snippet", "")
            results_summary.append(f"Result {i}: {title} - {snippet}")

        # Build the prompt for the AI
        prompt = f"""
        Based only on the following web search results, answer the user's question.
        - Always answer in the same language as the user's question (detected: {user_lang}).
        - Use only the information from the search results below.
        - If there is not enough information, say so.
        - Be brief and informative (no more than 2-3 sentences).
        - Cite the source if possible.
        - Do not make up information that is not present in the search results.
        - If there are conflicting data, mention it.

        User question: "{original_question}"
        Search query: "{search_query}"

        Search results:
        {chr(10).join(results_summary)}

        Answer:
        """

        answer = await get_35_ai_answer(prompt)
        if not answer or answer.lower().startswith("error"):
            # Fallback answer based on the first found snippet
            first_result = top_results[0]
            snippet = first_result.get("snippet", "")
            return f"Based on the found information: {snippet[:200]}..."

        return answer.strip()

    except Exception as e:
        logger.error(f"Error processing web search results: {e}")
        return "Sorry, an error occurred while retrieving information. Please try again later."


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
