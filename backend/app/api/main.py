from fastapi import FastAPI
from dotenv import load_dotenv
from app.api.endpoints import notes


app = FastAPI(title="PipGraph Backend")

# Подключаем роутер с WebSocket эндпоинтом
# Добавляем префикс для версионирования API
app.include_router(notes.router, prefix="/api/v1")

@app.get("/")
def read_root():
    return {"status": "PipGraph Backend is running"}