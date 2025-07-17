from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv
from fastapi.security import OAuth2PasswordBearer
import os

load_dotenv()


class Settings:
    app_name: str = "FastAPI"
    secret_key: str = os.getenv("SECRET_KEY")
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 2880
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


settings = Settings()
