from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv
from fastapi.security import OAuth2PasswordBearer
from typing import ClassVar

load_dotenv()


class Settings(BaseSettings):
    app_name: str = "FastAPI"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 2880

    database_url: str

    secret_key: str

    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_pass: str

    frontend_url: str

    gemini_api_key: str
    azure_openai_key: str
    azure_openai_endpoint: str
    azure_openai_deployment_name: str

    eleven_labs_api_key: str
    eleven_labs_voice_id: str

    serper_api_key: str

    ai_token_limit: int
    translate_symbols_limit: int
    voice_symbols_limit: int
    summarize_symbols_limit: int

    redis_url: str

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    oauth2_scheme: ClassVar[OAuth2PasswordBearer] = OAuth2PasswordBearer(
        tokenUrl="/auth/token"
    )


settings = Settings()
