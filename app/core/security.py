from datetime import datetime, timedelta
from jose import jwt
from passlib.context import CryptContext

from app.core.config import settings

import json
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from email.message import EmailMessage
from aiosmtplib import send


SECRET_KEY = settings.secret_key

SMTP_HOST = settings.smtp_host
SMTP_PORT = settings.smtp_port
SMTP_USER = settings.smtp_user
SMTP_PASS = settings.smtp_pass
FRONTEND_URL = settings.frontend_url

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


async def send_change_pass_confirmation_email(email: str, token: str):
    confirm_url = f"{FRONTEND_URL}/confirm-password?token={token}"

    message = EmailMessage()
    message["From"] = SMTP_USER
    message["To"] = email
    message["Subject"] = "Смена пароля"
    message.set_content(
        f"Здравствуйте!\n\nДля смены пароля перейдите по ссылке:\n{confirm_url}\n\n"
        "Если вы не пытались поменять пароль, просто проигнорируйте это письмо."
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
