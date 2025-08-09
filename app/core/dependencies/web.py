from edge_tts.exceptions import NoAudioReceived

import app.redis_client
from app.core.config import settings
from app.token_limit import check_voice_limit_only, increment_voice_limit
from app.services.summarize_service import summarize_text_full
from app.core.dependencies.utils import get_voice_summary_within_limit
from app.services.voice.speech import synthesize_speech_async

import logging
import json
import os
import aiohttp
import tempfile
import base64


logger = logging.getLogger(__name__)
serper_api_key = settings.serper_api_key
voice = settings.eleven_labs_voice_id


async def fetch_website(website_url: str):
    url = "https://scrape.serper.dev"
    payload = {"url": website_url}
    headers = {
        "X-API-KEY": serper_api_key,
        "Content-Type": "application/json",
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payload) as response:
            result = await response.text()
            return result


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

        summarized_text_to_voice = await summarize_text_full(
            truncated_data_to_voice, 2000
        )

        summarized_text_to_voice = await get_voice_summary_within_limit(
            redis, user_id, summarized_text_to_voice
        )

    else:
        truncated_data_to_voice = data_to_voice
        summarized_text_to_voice = truncated_data_to_voice

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


async def handle_web_search(query: str):
    url = "https://google.serper.dev/search"

    payload = json.dumps({"q": query})

    headers = {
        "X-API-KEY": serper_api_key,
        "Content-Type": "application/json",
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, data=payload) as response:
            return await response.json()
