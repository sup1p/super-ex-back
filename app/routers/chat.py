from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import AsyncSessionLocal

from app.models import ChatSession, Message, User
from app.schemas import ChatSessionMessageRead, ChatSessionRead

from app.core.dependencies import (
    get_db,
    get_current_user,
    get_ai_answer,
    handle_voice_websocket,
)
from app.core.config import settings

from jose import JWTError, jwt
from typing import List
import traceback


router = APIRouter()


@router.get("/chat/all", response_model=List[ChatSessionRead], tags=["Chat"])
async def get_all_chats(
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(ChatSession).where(ChatSession.user_id == current_user.id)
    )
    chats = result.scalars().all()
    return chats


@router.get(
    "/chat/messages/{chat_id}",
    response_model=List[ChatSessionMessageRead],
    tags=["Chat"],
)
async def get_all_messages(
    chat_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(ChatSession).where(
            (ChatSession.id == chat_id) & (ChatSession.user_id == current_user.id)
        )
    )
    chat = result.scalars().first()
    if chat is None:
        raise HTTPException(status_code=404, detail="No such chat")

    messages_result = await db.execute(
        select(Message).where(Message.session_id == chat.id)
    )
    messages = messages_result.scalars().all()
    return messages


@router.websocket("/chat/websocket")
async def websocket_chat(websocket: WebSocket):
    await websocket.accept()
    print("WebSocket чат соединение установлено")
    # Получаем токен из query params (например: ws://.../chat/send?token=...)
    token = websocket.query_params.get("token")
    if not token:
        await websocket.send_json({"error": "No token provided"})
        await websocket.close()
        return
    # Получаем пользователя по токену
    async with AsyncSessionLocal() as db:
        try:
            payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
            user_id: str = payload.get("sub")
            if not user_id:
                await websocket.send_json({"error": "Invalid token"})
                await websocket.close()
                return
        except JWTError:
            await websocket.send_json({"error": "Invalid token"})
            await websocket.close()
            return
        result = await db.execute(select(User).where(User.id == int(user_id)))
        user = result.scalar_one_or_none()
        if not user:
            await websocket.send_json({"error": "User not found"})
            await websocket.close()
            return
        chat_session = None
        first_message = None
        try:
            while True:
                data = await websocket.receive_text()
                print(f"Получено сообщение: {data}")
                if chat_session is None:
                    # Получаем название чата от ИИ
                    prompt = f"Придумай короткое название для чата по этому сообщению: {data}"
                    chat_name = await get_ai_answer(prompt)
                    chat_session = ChatSession(user_id=user.id, name=chat_name)
                    db.add(chat_session)
                    await db.commit()
                    await db.refresh(chat_session)
                    first_message = data
                # Сохраняем сообщение пользователя
                user_msg = Message(
                    session_id=chat_session.id, role="user", content=data
                )
                db.add(user_msg)
                await db.commit()
                # Получаем ответ от ИИ
                ai_answer = await get_ai_answer(data)
                # Сохраняем ответ ИИ
                ai_msg = Message(
                    session_id=chat_session.id, role="assistant", content=ai_answer
                )
                db.add(ai_msg)
                await db.commit()
                # Отправляем ответ пользователю
                response = {"text": ai_answer}
                await websocket.send_json(response)
                print("Ответ отправлен успешно")
        except WebSocketDisconnect:
            print("Клиент отключился от чата")
        except Exception as e:
            print(f"Ошибка WebSocket чата: {e}")
            traceback.print_exc()
            try:
                await websocket.close(code=1011, reason="Server error")
            except:
                pass


@router.websocket("/websocket-voice")
async def websocket_voice(websocket: WebSocket):
    await handle_voice_websocket(websocket)
