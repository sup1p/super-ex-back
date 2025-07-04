from fastapi import APIRouter, Depends


from app.models import User

from app.core.dependencies import get_current_user

from app.services import summarize

from app.schemas import SummaryRequest


router = APIRouter()


@router.post(
    "/tool/summarize",
    tags=["Tools"],
)
async def summarize_webpage(
    summary_request: SummaryRequest,
    current_user: User = Depends(get_current_user),
):
    return await summarize.summarize_text_full(summary_request.text, 2000)


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
