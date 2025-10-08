from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Neo4j Database Configuration
    NEO4J_URI: str
    NEO4J_USER: str
    NEO4J_PASSWORD: str

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