from fastapi import APIRouter, Depends, HTTPException

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, Event
from app.schemas import EventCreate, EventRead, EventUpdate

from app.core.dependencies import get_db, get_current_user


router = APIRouter()


@router.post(
    "/calendar/create",
    response_model=EventRead,
    tags=["Calendar"],
)
async def create_note(
    event: EventCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    new_calendar = Event(
        title=event.title,
        description=event.description,
        user_id=current_user.id,
        start_date=event.start_date.replace(tzinfo=None) if event.start_date else None,
        location=event.location,
        reminder=event.reminder,
    )
    db.add(new_calendar)
    await db.commit()
    await db.refresh(new_calendar)
    return new_calendar


@router.get("/calendar/get/all", response_model=list[EventRead], tags=["Calendar"])
async def get_all_notes(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    events = await db.execute(select(Event).where(Event.user_id == current_user.id))
    if events is None:
        return []
    return events.scalars().all()


@router.get("/calendar/get/{event_id}", response_model=EventRead, tags=["Calendar"])
async def get_event(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    event = await db.get(Event, event_id)
    if event is None or event.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@router.patch(
    "/calendar/update/{event_id}", response_model=EventRead, tags=["Calendar"]
)
async def update_event(
    event_id: int,
    updated_event: EventUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    event = await db.get(Event, event_id)
    if event is None or event.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Event not found")
    if updated_event.title is not None:
        event.title = updated_event.title
    if updated_event.description is not None:
        event.description = updated_event.description
    if updated_event.start_date is not None:
        event.start_date = (
            updated_event.start_date.replace(tzinfo=None)
            if updated_event.start_date
            else None
        )
    if updated_event.location is not None:
        event.location = updated_event.location
    if updated_event.reminder is not None:
        event.reminder = updated_event.reminder
    await db.commit()
    await db.refresh(event)
    return event


@router.delete("/calendar/delete/{event_id}", tags=["Calendar"])
async def delete_event(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    event = await db.get(Event, event_id)
    if event is None or event.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Event not found")
    await db.delete(event)
    await db.commit()
    return "Deleted"
