import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config.settings import settings

# Настройка логирования для backend (до импорта модулей)
log_level = settings.LOG_LEVEL.upper()
logging.basicConfig(
    level=logging.INFO,  # Базовый уровень для всех
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# # DEBUG только для модулей приложения
# if log_level == "DEBUG":
logging.getLogger("app.services").setLevel(logging.DEBUG)
logging.getLogger("app.crud").setLevel(logging.DEBUG)

# Заглушить шумные библиотеки
logging.getLogger("neo4j").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

print(f"🔧 Logging level set to: {log_level}")
from app.api.endpoints import dev


app = FastAPI(title="PipGraph Backend")

# CORS настройки для разработки
# Разрешаем запросы с frontend (localhost:3000) и других источников
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # Next.js dev server
        "http://localhost:3001",  # Alternative port
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],  # Разрешить все методы (GET, POST, PUT, DELETE, etc.)
    allow_headers=["*"],  # Разрешить все заголовки
)

# REST API роутеры
app.include_router(dev.router, prefix="/api/v1")

@app.get("/")
def read_root():
    return {"status": "PipGraph Backend is running"}