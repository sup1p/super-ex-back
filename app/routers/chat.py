from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import AsyncSessionLocal

from app.models import ChatSession, Message, User
from app.schemas import ChatSessionMessageRead, ChatSessionRead

from app.core.dependencies import (
    get_db,
    get_current_user,
)
from app.core.config import settings
from app.services.voice import (
    get_ai_answer,
    get_35_ai_answer,
    needs_web_search,
    process_web_search_results,
)

from jose import JWTError, jwt
from typing import List
import logging

logger = logging.getLogger(__name__)


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


@router.delete("/chat/delete", tags=["Chat"])
async def delete_chat(
    chat_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    chat = await db.get(ChatSession, chat_id)
    logger.info("dasdasdasdas")
    logger.info(chat)
    if chat is None or chat.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Chat not found")
    await db.delete(chat)
    await db.commit()
    return "Deleted"


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
    logger = logging.getLogger(__name__)
    logger.info("WebSocket чат соединение установлено")
    # Получаем токен из query params (например: ws://.../chat/send?token=...)
    token = websocket.query_params.get("token")
    chat_id = websocket.query_params.get("chat_id")
    if not token:
        await websocket.send_json({"error": "No token provided"})
        await websocket.close()
        logger.error("WebSocket закрыт: не передан токен.")
        return
    # Получаем пользователя по токену
    async with AsyncSessionLocal() as db:
        try:
            payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
            user_id: str = payload.get("sub")
            if not user_id:
                await websocket.send_json({"error": "Invalid token"})
                await websocket.close()
                logger.error("WebSocket закрыт: некорректный токен (нет user_id).")
                return
        except JWTError:
            await websocket.send_json({"error": "Invalid token"})
            await websocket.close()
            logger.error("WebSocket закрыт: некорректный токен (JWTError).")
            return
        result = await db.execute(select(User).where(User.id == int(user_id)))
        user = result.scalar_one_or_none()
        if not user:
            await websocket.send_json({"error": "User not found"})
            await websocket.close()
            logger.error(f"WebSocket закрыт: пользователь с id {user_id} не найден.")
            return
        chat_session = None
        if chat_id:
            result = await db.execute(
                select(ChatSession).where(
                    (ChatSession.id == int(chat_id)) & (ChatSession.user_id == user.id)
                )
            )
            chat_session = result.scalars().first()
            if not chat_session:
                await websocket.send_json({"error": "Chat not found"})
                await websocket.close()
                return
        if chat_id and chat_session:
            # Если пользователь подключился к существующему чату, отправим историю сообщений
            messages_result = await db.execute(
                select(Message).where(Message.session_id == chat_session.id)
            )
            messages = messages_result.scalars().all()
            history = [{"role": msg.role, "content": msg.content} for msg in messages]
            await websocket.send_json({"history": history})
        first_message = None
        try:
            while True:
                data = await websocket.receive_text()
                logger.info(f"Получено сообщение: {data}")
                if chat_session is None:
                    # Получаем название чата от ИИ
                    prompt = f"Придумай короткое название для чата по этому сообщению. Ответь ТОЛЬКО ОДНИМ СЛОВОМ: {data}"
                    chat_name = await get_ai_answer(prompt)
                    chat_session = ChatSession(user_id=user.id, name=chat_name)
                    db.add(chat_session)
                    await db.commit()
                    await db.refresh(chat_session)
                    first_message = data
                    logger.info(f"Создан новый чат с названием: {chat_name}")
                # Сохраняем сообщение пользователя
                user_msg = Message(
                    session_id=chat_session.id, role="user", content=data
                )
                db.add(user_msg)
                await db.commit()
                logger.info(f"Сохранено сообщение пользователя в чат {chat_session.id}")

                # Проверяем, нужен ли веб-поиск для ответа
                needs_search, search_query = await needs_web_search(data)

                if needs_search and search_query:
                    logger.info(f"Требуется веб-поиск для запроса: {search_query}")
                    # Отправляем промежуточное сообщение о поиске
                    await websocket.send_json(
                        {
                            "text": "Searching for actual information..",
                            "searching": True,
                        }
                    )

                    # Выполняем поиск и обрабатываем результаты
                    ai_answer = await process_web_search_results(search_query, data)
                    logger.info(f"Получен ответ на основе веб-поиска: {ai_answer}")
                else:
                    # Получаем обычный ответ от ИИ
                    ai_answer = await get_35_ai_answer(data)
                    logger.info(f"Получен обычный ответ от ИИ: {ai_answer}")

                # Сохраняем ответ ИИ
                ai_msg = Message(
                    session_id=chat_session.id, role="assistant", content=ai_answer
                )
                db.add(ai_msg)
                await db.commit()
                logger.info(f"Сохранён ответ ИИ в чат {chat_session.id}")
                # Отправляем ответ пользователю
                response = {"text": ai_answer}
                await websocket.send_json(response)
                logger.info("Ответ отправлен успешно")
        except WebSocketDisconnect:
            logger.info("Клиент отключился от чата")
        except Exception as e:
            logger.error(f"Ошибка WebSocket чата: {e}", exc_info=True)
            try:
                await websocket.close(code=1011, reason="Server error")
            except:
                logger.error("Не удалось закрыть WebSocket после ошибки.")
