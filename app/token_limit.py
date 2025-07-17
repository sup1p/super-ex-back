from fastapi import HTTPException
import os
from datetime import date
import logging

AI_TOKEN_LIMIT = os.getenv("AI_TOKEN_LIMIT")
TRANSLATE_SYMBOLS_LIMIT = os.getenv("TRANSLATE_SYMBOLS_LIMIT")
VOICE_SYMBOLS_LIMIT = os.getenv("VOICE_SYMBOLS_LIMIT")
SUMMARIZE_SYMBOLS_LIMIT = os.getenv("SUMMARIZE_SYMBOLS_LIMIT")

logger = logging.getLogger(__name__)


async def check_ai_limit_only(redis, user_id, tokens_needed: int):
    if redis is None:
        raise RuntimeError("Redis client is not initialized!")
    today = date.today().isoformat()
    key = f"tokens:{user_id}:{today}"

    current = await redis.get(key)
    current = int(current) if current else 0

    logger.info(
        f"[TokenLimit] user_id={user_id} | today={today} | current={current} | needed={tokens_needed} | limit={AI_TOKEN_LIMIT}"
    )

    if current + tokens_needed > int(AI_TOKEN_LIMIT):
        logger.warning(
            f"[TokenLimit] LIMIT EXCEEDED: user_id={user_id} | attempted={current + tokens_needed} | limit={AI_TOKEN_LIMIT}"
        )
        raise HTTPException(status_code=429, detail="Token limit exceeded")


async def increment_ai_limit(redis, user_id: str, tokens_needed: int):
    if redis is None:
        raise RuntimeError("Redis client is not initialized!")
    today = date.today().isoformat()
    key = f"tokens:{user_id}:{today}"

    current = await redis.get(key)
    current = int(current) if current else 0

    await redis.incrby(key, tokens_needed)
    logger.info(
        f"[TokenLimit] user_id={user_id} | new_total={current + tokens_needed} (added {tokens_needed})"
    )
    if current == 0:
        await redis.expire(key, 86400)
        logger.info(
            f"[TokenLimit] user_id={user_id} | key set to expire in 86400s (1 day)"
        )


async def check_translate_limit_only(redis, user_id: str, symbols_needed: int):
    if redis is None:
        raise RuntimeError("Redis client is not initialized!")
    today = date.today().isoformat()
    key = f"translate_symbols:{user_id}:{today}"

    current = await redis.get(key)
    current = int(current) if current else 0

    logger.info(
        f"[TranslateSymbolsLimitCheck] user_id={user_id} | today={today} | current={current} | needed={symbols_needed} | limit={TRANSLATE_SYMBOLS_LIMIT}"
    )

    if current + symbols_needed > int(TRANSLATE_SYMBOLS_LIMIT):
        logger.warning(
            f"[TranslateSymbolsLimitCheck] LIMIT EXCEEDED: user_id={user_id} | attempted={current + symbols_needed} | limit={TRANSLATE_SYMBOLS_LIMIT}"
        )
        raise HTTPException(status_code=429, detail="Symbols limit exceeded")


async def increment_translate_limit(redis, user_id: str, symbols_needed: int):
    if redis is None:
        raise RuntimeError("Redis client is not initialized!")
    today = date.today().isoformat()
    key = f"translate_symbols:{user_id}:{today}"

    current = await redis.get(key)
    current = int(current) if current else 0

    await redis.incrby(key, symbols_needed)
    logger.info(
        f"[TranslateSymbolsLimit] user_id={user_id} | new_total={current + symbols_needed} (added {symbols_needed})"
    )
    if current == 0:
        await redis.expire(key, 86400)
        logger.info(
            f"[TranslateSymbolsLimit] user_id={user_id} | key set to expire in 86400s (1 day)"
        )


async def check_voice_limit_only(redis, user_id: str, symbols_needed: int):
    if redis is None:
        raise RuntimeError("Redis client is not initialized!")
    today = date.today().isoformat()
    key = f"voice_symbols:{user_id}:{today}"

    current = await redis.get(key)
    current = int(current) if current else 0

    logger.info(
        f"[VoiceSymbolsLimitCheck] user_id={user_id} | today={today} | current={current} | needed={symbols_needed} | limit={VOICE_SYMBOLS_LIMIT}"
    )

    if current + symbols_needed > int(VOICE_SYMBOLS_LIMIT):
        logger.warning(
            f"[VoiceSymbolsLimitCheck] LIMIT EXCEEDED: user_id={user_id} | attempted={current + symbols_needed} | limit={VOICE_SYMBOLS_LIMIT}"
        )
        raise HTTPException(status_code=429, detail="Symbols limit exceeded")


async def increment_voice_limit(redis, user_id: str, symbols_needed: int):
    if redis is None:
        raise RuntimeError("Redis client is not initialized!")
    today = date.today().isoformat()
    key = f"voice_symbols:{user_id}:{today}"

    current = await redis.get(key)
    current = int(current) if current else 0

    await redis.incrby(key, symbols_needed)
    logger.info(
        f"[VoiceSymbolsLimit] user_id={user_id} | new_total={current + symbols_needed} (added {symbols_needed})"
    )
    if current == 0:
        await redis.expire(key, 86400)
        logger.info(
            f"[VoiceSymbolsLimit] user_id={user_id} | key set to expire in 86400s (1 day)"
        )


async def check_summarize_limit_only(redis, user_id: str, symbols_needed: int):
    if redis is None:
        raise RuntimeError("Redis client is not initialized!")
    today = date.today().isoformat()
    key = f"summarize_symbols:{user_id}:{today}"

    current = await redis.get(key)
    current = int(current) if current else 0

    logger.info(
        f"[SummarizeSymbolsLimitCheck] user_id={user_id} | today={today} | current={current} | needed={symbols_needed} | limit={SUMMARIZE_SYMBOLS_LIMIT}"
    )

    if current + symbols_needed > int(SUMMARIZE_SYMBOLS_LIMIT):
        logger.warning(
            f"[SummarizeSymbolsLimitCheck] LIMIT EXCEEDED: user_id={user_id} | attempted={current + symbols_needed} | limit={SUMMARIZE_SYMBOLS_LIMIT}"
        )
        raise HTTPException(status_code=429, detail="Symbols limit exceeded")


async def increment_summarize_limit(redis, user_id: str, symbols_needed: int):
    if redis is None:
        raise RuntimeError("Redis client is not initialized!")
    today = date.today().isoformat()
    key = f"summarize_symbols:{user_id}:{today}"

    current = await redis.get(key)
    current = int(current) if current else 0

    await redis.incrby(key, symbols_needed)
    logger.info(
        f"[SummarizeSymbolsLimit] user_id={user_id} | new_total={current + symbols_needed} (added {symbols_needed})"
    )
    if current == 0:
        await redis.expire(key, 86400)
        logger.info(
            f"[SummarizeSymbolsLimit] user_id={user_id} | key set to expire in 86400s (1 day)"
        )
