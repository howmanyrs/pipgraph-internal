from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Neo4j Database Configuration
    NEO4J_URI: str
    NEO4J_USER: str
    NEO4J_PASSWORD: str


    # Cloud.ru LLM Configuration
    CLOUDRU_API_KEY: str
    CLOUDRU_BASE_URL: str = "https://foundation-models.api.cloud.ru/v1"
    CLOUDRU_MAIN_MODEL: str = "Qwen/Qwen3-235B-A22B-Instruct-2507"
    CLOUDRU_SMALL_MODEL: str = "t-tech/T-lite-it-1.0"
    CLOUDRU_EMBEDDING_MODEL: str = "Qwen/Qwen3-Embedding-0.6B"

    # OpenRouter LLM Configuration
    OPENROUTER_API_KEY: str
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    OPENROUTER_MAIN_MODEL: str = "anthropic/claude-3.5-sonnet"
    OPENROUTER_SMALL_MODEL: str = "anthropic/claude-3-haiku"
    OPENROUTER_EMBEDDING_MODEL: str = "openai/text-embedding-3-small"

    # Legacy (kept for backward compatibility)
    OPENAI_API_KEY: str = ""  # Optional, can be removed if not used elsewhere

    # DATABASE_URL: str = "sqlite+aiosqlite:///./temp.db"
    # OPENAI_API_URL: str = "https://bothub.chat/api/v2/openai/v1"
    # MAX_TESTS_PER_DAY: int = 5 # Максимальное количество тестов в день на пользователя

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding='utf-8', extra='ignore')


settings = Settings()