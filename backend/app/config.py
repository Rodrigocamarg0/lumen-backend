import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    MODEL_ID: str = "google/gemma-4-E4B-it"
    QUANTIZATION_BITS: float = 3.5
    OUTLIER_THRESHOLD: float = 10.0
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    USE_TURBOQUANT_CACHE: bool = False
    KV_CACHE_BITS: float = 3.5
    KV_CACHE_OUTLIER_THRESHOLD: float = 10.0
    OPENAI_API_KEY: str = ""
    HF_TOKEN: str = ""

    class Config:
        env_file = ".env"


settings = Settings()

# Expose tokens to their respective SDKs automatically
if settings.OPENAI_API_KEY:
    os.environ.setdefault("OPENAI_API_KEY", settings.OPENAI_API_KEY)
if settings.HF_TOKEN:
    os.environ.setdefault("HF_TOKEN", settings.HF_TOKEN)
