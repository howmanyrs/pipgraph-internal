import logging

from fastapi import FastAPI

from config.settings import settings

# Настройка логирования для backend (до импорта модулей)
log_level = settings.LOG_LEVEL.upper()
logging.basicConfig(
    level=logging.INFO,  # Базовый уровень для всех
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# DEBUG только для модулей приложения
if log_level == "DEBUG":
    logging.getLogger("app.api.endpoints.suggestions").setLevel(logging.DEBUG)
    logging.getLogger("app.api.endpoints.workflow").setLevel(logging.DEBUG)
    logging.getLogger("app.workflows").setLevel(logging.DEBUG)
    logging.getLogger("app.services").setLevel(logging.DEBUG)
    logging.getLogger("app.crud").setLevel(logging.DEBUG)

# Заглушить шумные библиотеки
logging.getLogger("neo4j").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

print(f"🔧 Logging level set to: {log_level}")
from app.api.endpoints import notes
from app.api.endpoints import workflow as workflow_endpoints
from app.api.endpoints import suggestions
from app.api.websockets import workflow


app = FastAPI(title="PipGraph Backend")

# Подключаем REST API роутеры
app.include_router(notes.router, prefix="/api/v1")

# Новые REST API роутеры (v1)
app.include_router(workflow_endpoints.router, prefix="/api/v1")
app.include_router(suggestions.router, prefix="/api/v1")

# Подключаем WebSocket роутеры (без префикса для простоты)
app.include_router(workflow.router)

@app.get("/")
def read_root():
    return {"status": "PipGraph Backend is running"}