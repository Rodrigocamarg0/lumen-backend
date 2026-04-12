import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    MODEL_ID: str = "google/gemma-4-E4B-it"
    QUANTIZATION_BITS: float = 3.5
    OUTLIER_THRESHOLD: float = 10.0
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
    HF_TOKEN: str = ""

    class Config:
        env_file = ".env"


settings = Settings()

# Expose the token to huggingface_hub / transformers automatically
if settings.HF_TOKEN:
    os.environ.setdefault("HF_TOKEN", settings.HF_TOKEN)
