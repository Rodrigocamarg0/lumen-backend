import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # LLM provider: "local" (Gemma via HF/MLX) or "openai"
    LLM_PROVIDER: str = "local"
    OPENAI_MODEL: str = "gpt-4.1-nano"
    # Reasoning effort for OpenAI thinking models: low | medium | high | xhigh
    # Leave empty to disable thinking mode.
    OPENAI_REASONING_EFFORT: str = ""

    MODEL_ID: str = "google/gemma-4-E4B-it"
    QUANTIZATION_BITS: float = 3.5
    OUTLIER_THRESHOLD: float = 10.0
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    USE_TURBOQUANT_CACHE: bool = False
    KV_CACHE_BITS: float = 3.5
    KV_CACHE_OUTLIER_THRESHOLD: float = 10.0
    MAX_NEW_TOKENS: int = 512
    # Force device_map="cuda" when free VRAM >= this threshold (MB).
    # Prevents "auto" from spilling layers to CPU on small-VRAM cards.
    MIN_VRAM_MB_FOR_GPU_ONLY: int = 1800
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
