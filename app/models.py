from sqlalchemy import String, Integer, Column, ForeignKey, DateTime, Text
from sqlalchemy.orm import relationship
from datetime import datetime


from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, default=None)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)

    notes = relationship("Notes", back_populates="user", cascade="all, delete-orphan")
    sessions = relationship(
        "ChatSession", back_populates="user", cascade="all, delete-orphan"
    )


class Notes(Base):
    __tablename__ = "notes"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String)
    content = Column(String)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))

    user = relationship("User", back_populates="notes")


class ChatSession(Base):
    __tablename__ = "chat_session"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    name = Column(String, index=True)

    user = relationship("User", back_populates="sessions")
    messages = relationship(
        "Message", back_populates="session", cascade="all, delete-orphan"
    )


class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("chat_session.id"))
    role = Column(String)
    content = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)

    session = relationship("ChatSession", back_populates="messages")
