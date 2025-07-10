from pydantic import BaseModel, EmailStr
from datetime import datetime


class EmailSchema(BaseModel):
    email: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ChangePasswordRequest(BaseModel):
    new_password: str
    token: str


class ChatSessionRead(BaseModel):
    id: int
    created_at: datetime
    name: str
    user_id: int


class ChatSessionMessageRead(BaseModel):
    id: int
    role: str
    content: str
    timestamp: datetime


class NoteCreate(BaseModel):
    title: str
    content: str


class NoteRead(BaseModel):
    id: int
    title: str
    content: str
    user_id: int

    class Config:
        orm_mode = True


class NoteUpdate(BaseModel):
    title: str | None = None
    content: str | None = None


class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str


class UserRead(BaseModel):
    id: int
    email: EmailStr
    name: str

    class Config:
        orm_mode = True


class RegisterRequest(BaseModel):
    email: EmailStr
    name: str
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class SummaryRequest(BaseModel):
    url: str


class TextRequest(BaseModel):
    text: str
