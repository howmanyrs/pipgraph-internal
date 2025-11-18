from fastapi import FastAPI
from dotenv import load_dotenv
from app.api.endpoints import notes
from app.api.websockets import workflow


app = FastAPI(title="PipGraph Backend")

# Подключаем REST API роутеры
app.include_router(notes.router, prefix="/api/v1")

# Подключаем WebSocket роутеры (без префикса для простоты)
app.include_router(workflow.router)

@app.get("/")
def read_root():
    return {"status": "PipGraph Backend is running"}