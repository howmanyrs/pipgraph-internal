from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    OPENAI_API_KEY: str
    NEO4J_URI: str
    NEO4J_USER: str
    NEO4J_PASSWORD: str
    # DATABASE_URL: str = "sqlite+aiosqlite:///./temp.db"
    # OPENAI_API_URL: str = "https://bothub.chat/api/v2/openai/v1"
    # MAX_TESTS_PER_DAY: int = 5 # Максимальное количество тестов в день на пользователя

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding='utf-8', extra='ignore')
    

settings = Settings()