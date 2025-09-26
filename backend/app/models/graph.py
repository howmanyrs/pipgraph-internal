from pydantic import BaseModel, Field
from typing import List, Dict, Any

class Node(BaseModel):
    """Модель узла в графе."""
    id: str
    label: str
    properties: Dict[str, Any]

class Relationship(BaseModel):
    """Модель связи в графе."""
    source_id: str
    target_id: str
    type: str
    properties: Dict[str, Any] = Field(default_factory=dict)

class GraphData(BaseModel):
    """Модель для представления извлеченных из заметки графовых данных."""
    nodes: List[Node]
    relationships: List[Relationship]