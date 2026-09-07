"""
Edu-Voice-Ai — Backend Core Configuration
Loads and validates all typed environment variables via Pydantic BaseSettings.
"""

from typing import List, Union
from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # 1. Application & Server
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    PROJECT_NAME: str = "Edu-Voice-Ai Backend"
    API_V1_STR: str = "/api/v1"
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
    ]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)

    # 2. Supabase PostgreSQL & Authentication (Server Secrets)
    SUPABASE_URL: str = "https://ccydagfljcdnkkobyhwx.supabase.co"
    SUPABASE_ANON_KEY: str = "sb_publishable_8lvXhuJamTZ2xmlwCulnTw_N8q2mdLq"
    SUPABASE_SERVICE_ROLE_KEY: str = "placeholder_service_role_key"
    SUPABASE_JWT_SECRET: str = "placeholder_jwt_secret"

    DATABASE_URL: str = "postgresql+asyncpg://postgres:placeholder@localhost:5432/postgres"
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10

    @property
    def async_database_url(self) -> str:
        """Ensure DATABASE_URL uses the asyncpg driver."""
        url = self.DATABASE_URL
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+asyncpg://", 1)
        return url

    # 3. LLM Engine (Groq)
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    GROQ_TEMPERATURE: float = 0.2
    GROQ_MAX_TOKENS: int = 1024

    # 4. Embeddings & RAG
    EMBEDDING_MODEL: str = "BAAI/bge-m3"
    EMBEDDING_DIMENSION: int = 1024
    RAG_TOP_K: int = 5
    RAG_SIMILARITY_THRESHOLD: float = 0.65

    # 5. Voice Engine (Separate Service / Container)
    VOICE_ENGINE_URL: str = "http://localhost:8001"
    VOICE_ENGINE_API_KEY: str = ""
    VOICE_ENGINE_TIMEOUT_SECONDS: int = 10

    # 6. Telephony (Exotel) & Internal Service Auth
    INTERNAL_SERVICE_KEY: str = "placeholder_internal_service_key"
    EXOTEL_ACCOUNT_SID: str = ""
    EXOTEL_API_KEY: str = ""
    EXOTEL_API_TOKEN: str = ""
    EXOTEL_SUB_DOMAIN: str = "api.exotel.com"
    EXOTEL_CALLER_ID: str = ""
    EXOTEL_WEBHOOK_SECRET: str = ""

    # 7. AWS / S3 Storage
    AWS_REGION: str = "ap-south-1"
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    S3_BUCKET_DOCUMENTS: str = "edu-voice-documents-dev"
    S3_BUCKET_RECORDINGS: str = "edu-voice-recordings-dev"


settings = Settings()
