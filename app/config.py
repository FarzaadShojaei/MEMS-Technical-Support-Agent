"""Central configuration. Everything overridable via environment variables or .env."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # --- Paths ---
    raw_data_dir: str = "data/raw"
    index_dir: str = "data/index"
    collection_name: str = "lsm6dsox"

    # --- Chunking ---
    chunk_size: int = 1000  # characters
    chunk_overlap: int = 150

    # --- Embeddings (local, free by default) ---
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    # --- Retrieval ---
    top_k: int = 5

    # --- LLM (any OpenAI-compatible endpoint) ---
    # OpenAI:      base_url=https://api.openai.com/v1   llm_api_key=sk-...
    # Ollama:      base_url=http://localhost:11434/v1   llm_api_key=ollama
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = "CHANGE_ME"
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.0
    llm_max_tokens: int = 700

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
