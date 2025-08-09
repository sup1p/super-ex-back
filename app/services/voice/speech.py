from app.core.config import settings
from faster_whisper import WhisperModel

import aiohttp
import logging


logger = logging.getLogger(__name__)

ELEVEN_LABS_API_KEY = settings.eleven_labs_api_key


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
