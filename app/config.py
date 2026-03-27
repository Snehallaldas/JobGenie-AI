from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    APP_NAME: str = "AI Interview Coach API"
    DEBUG: bool = True
    DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost:5432/interview_db"
    MISTRAL_API_KEY: str = ""
    MISTRAL_LARGE_MODEL: str = "mistral-large-latest"
    MISTRAL_SMALL_MODEL: str = "mistral-small-latest"
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    CHROMA_PERSIST_DIR: str = "./chroma_db"
    UPLOAD_DIR: str = "./uploads"
    MAX_FILE_SIZE_MB: int = 10

    class Config:
        env_file = ".env"

@lru_cache()
def get_settings():
    return Settings()