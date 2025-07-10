from fastapi import APIRouter, Depends, Query

from googletrans import Translator

from app.models import User

from app.core.dependencies import get_current_user, fetch_website

from app.services import summarize

from app.schemas import SummaryRequest, TextRequest

import logging


router = APIRouter()
translator = Translator()
logger = logging.getLogger(__name__)


@router.post("/tool/summarize")
async def summarize_webpage(
    text_request: TextRequest, current_user: User = Depends(get_current_user)
):
    logger.info(f"TEXT CAME TO SUMMARIZE: {text_request.text}")
    truncated_text = text_request.text[:8000]
    logger.info(f"TRUNCATED TEXT TO SUMMARIZE: {truncated_text}")
    return await summarize.summarize_text_full(truncated_text, 2000)


@router.post(
    "/tool/summarize/new",
    tags=["Tools"],
)
async def summarize_webpage_new(
    summary_request: SummaryRequest,
    current_user: User = Depends(get_current_user),
):
    logger.info(f"Website came to summarize: {summary_request.url}")
    website_text = await fetch_website(summary_request.url)
    logger.info(f"TRUNCATED TEXT TO SUMMARIZE: {website_text}")
    truncated_website_text = website_text[:8000]
    return await summarize.summarize_text_full(truncated_website_text, 2000)


@router.post("/tools/summarize/selected", tags=["Tools"])
async def summarize_text(
    summarize_request: TextRequest, current_user: User = Depends(get_current_user)
):
    text_to_summarize = summarize_request.text

    truncated_text_to_summarize = text_to_summarize[:5000]

    summarized_text = await summarize.summarize_text_full(
        truncated_text_to_summarize, 3000
    )

    logger.info(f"Sent summarized text to client: {text_to_summarize}")
    return {"summarized_text": summarized_text}


# @router.get("/tools/simplify/{note_id}", tags=["Tools"])
# async def get_note(
#     note_id: int,
#     db: AsyncSession = Depends(get_db),
#     current_user: User = Depends(get_current_user),
# ):
#     note = await db.get(Notes, note_id)
#     if note is None or note.user_id != current_user.id:
#         raise HTTPException(status_code=404, detail="Note not found")
#     return note
