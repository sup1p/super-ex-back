from fastapi import APIRouter, Depends, HTTPException

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Notes, User
from app.schemas import NoteCreate, NoteRead, NoteUpdate

from app.core.dependencies.utils import get_current_user
from app.core.database import get_db


router = APIRouter()


@router.post(
    "/notes/create",
    response_model=NoteRead,
    tags=["Note"],
)
async def create_note(
    note: NoteCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    new_note = Notes(title=note.title, content=note.content, user_id=current_user.id)
    db.add(new_note)
    await db.commit()
    await db.refresh(new_note)
    return new_note


@router.get("/notes/get/all", response_model=list[NoteRead], tags=["Note"])
async def get_all_notes(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    notes = await db.execute(select(Notes).where(Notes.user_id == current_user.id))
    if notes is None:
        return []
    return notes.scalars().all()


@router.get("/notes/get/{note_id}", response_model=NoteRead, tags=["Note"])
async def get_note(
    note_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    note = await db.get(Notes, note_id)
    if note is None or note.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Note not found")
    return note


@router.patch("/notes/update/{note_id}", response_model=NoteRead, tags=["Note"])
async def update_note(
    note_id: int,
    updated_note: NoteUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    note = await db.get(Notes, note_id)
    if note is None or note.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Note not found")
    if updated_note.title is not None:
        note.title = updated_note.title
    if updated_note.content is not None:
        note.content = updated_note.content
    await db.commit()
    await db.refresh(note)
    return note


@router.delete("/notes/delete/{note_id}", tags=["Note"])
async def delete_note(
    note_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    note = await db.get(Notes, note_id)
    if note is None or note.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Note not found")
    await db.delete(note)
    await db.commit()
    return "Deleted"
