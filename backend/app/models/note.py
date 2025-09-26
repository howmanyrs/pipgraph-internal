from pydantic import BaseModel

class NotePayload(BaseModel):
    """Модель данных для входящей заметки."""
    file_path: str
    content: str