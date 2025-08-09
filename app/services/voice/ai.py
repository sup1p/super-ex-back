from app.core.config import settings

import httpx
import asyncio
import logging

logger = logging.getLogger(__name__)

GEMINI_API_KEY = settings.gemini_api_key
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
AZURE_OPENAI_ENDPOINT = settings.azure_openai_endpoint
AZURE_OPENAI_KEY = settings.azure_openai_key


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
