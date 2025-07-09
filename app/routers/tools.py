from fastapi import APIRouter, Depends


from app.models import User

from app.core.dependencies import get_current_user, fetch_website

from app.services import summarize

from app.schemas import SummaryRequest

import logging


router = APIRouter()
logger = logging.getLogger(__name__)


@router.post(
    "/tool/summarize",
    tags=["Tools"],
)
async def summarize_webpage(
    summary_request: SummaryRequest,
    current_user: User = Depends(get_current_user),
):
    logger.info(f"Website came to summarize: {summary_request.url}")
    website_text = await fetch_website(summary_request.url)
    logger.info(f"TRUNCATED TEXT TO SUMMARIZE: {website_text}")
    truncated_website_text = website_text[:8000]
    return await summarize.summarize_text_full(truncated_website_text, 2000)


# @router.post("/tool/summarize-new")
# async def summarize_webpage_new(
#     summary_request: ,
#     current_user: User = Depends(get_current_user),
# ):
#     logger.info(f"Website came to summarize: {summary_request}")


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
