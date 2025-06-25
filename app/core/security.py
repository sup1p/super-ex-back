from datetime import datetime, timedelta
from jose import jwt
from passlib.context import CryptContext

from app.core.config import settings

import os
import json
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from dotenv import load_dotenv

from email.message import EmailMessage
from aiosmtplib import send

load_dotenv()


SECRET_KEY = os.getenv("SECRET_KEY")
SALT = "email-confirmation"

serializer = URLSafeTimedSerializer(SECRET_KEY)


def generate_email_token(payload: dict) -> str:
    """Генерирует токен из словаря (имя, email, хеш пароля)"""
    json_data = json.dumps(payload)
    return serializer.dumps(json_data, salt=SALT)


def verify_email_token(token: str, max_age: int = 3600) -> dict:
    """Расшифровывает токен и возвращает словарь"""
    try:
        json_data = serializer.loads(token, salt=SALT, max_age=max_age)
        return json.loads(json_data)
    except SignatureExpired:
        raise ValueError("Токен истёк")
    except BadSignature:
        raise ValueError("Токен недействителен")


SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
FRONTEND_URL = os.getenv("FRONTEND_URL")  # например: http://localhost:5173


async def send_confirmation_email(email: str, token: str):
    confirm_url = f"{FRONTEND_URL}/confirm-email?token={token}"

    message = EmailMessage()
    message["From"] = SMTP_USER
    message["To"] = email
    message["Subject"] = "Подтверждение регистрации"
    message.set_content(
        f"Здравствуйте!\n\nДля завершения регистрации перейдите по ссылке:\n{confirm_url}\n\n"
        "Если вы не регистрировались, просто проигнорируйте это письмо."
    )

    await send(
        message,
        hostname=SMTP_HOST,
        port=SMTP_PORT,
        username=SMTP_USER,
        password=SMTP_PASS,
        start_tls=True,
    )


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return pwd_context.verify(password, hashed)


def create_access_token(subject: str, expires_delta: int | None = None) -> str:
    expire = datetime.utcnow() + timedelta(
        minutes=expires_delta or settings.access_token_expire_minutes
    )
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)
