from fastapi import APIRouter, Depends, Query

from googletrans import Translator

from app.models import User

from app.core.dependencies import get_current_user, fetch_website

from app.services import summarize

from app.schemas import SummaryRequest, TextRequest

import logging

from app.token_limit import check_summarize_limit_only, increment_summarize_limit
import app.redis_client


router = APIRouter()
translator = Translator()
logger = logging.getLogger(__name__)


@router.post(
    "/tool/summarize/new",
    tags=["Tools"],
)
async def summarize_webpage_new(
    summary_request: SummaryRequest,
    current_user: User = Depends(get_current_user),
):
    user_id = str(current_user.id)
    redis = app.redis_client.redis
    logger.info(f"Website came to summarize: {summary_request.url}")

    await check_summarize_limit_only(redis, user_id, 1001)

    website_text = await fetch_website(summary_request.url)
    truncated_website_text = website_text[:8000]
    logger.info(f"TRUNCATED TEXT TO SUMMARIZE: {truncated_website_text}")
    symbols_needed = len(truncated_website_text)
    await check_summarize_limit_only(
        redis, user_id, symbols_needed
    )  # returns 429 if limit exceeded
    summarized_text = await summarize.summarize_text_full(truncated_website_text, 2000)
    await increment_summarize_limit(redis, user_id, symbols_needed)
    return summarized_text


@router.post("/tools/summarize/selected", tags=["Tools"])
async def summarize_text(
    summarize_request: TextRequest, current_user: User = Depends(get_current_user)
):
    text_to_summarize = summarize_request.text

    truncated_text_to_summarize = text_to_summarize[:5000]

    user_id = str(current_user.id)
    symbols_needed = len(truncated_text_to_summarize)
    redis = app.redis_client.redis
    await check_summarize_limit_only(
        redis, user_id, symbols_needed
    )  # returns 429 if limit exceeded
    summarized_text = await summarize.summarize_text_full(
        truncated_text_to_summarize, 3000
    )
    await increment_summarize_limit(redis, user_id, symbols_needed)
    logger.info(f"Sent summarized text to client: {text_to_summarize}")
    return {"summarized_text": summarized_text}
