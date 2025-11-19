# Модели данных

**Дата обновления:** 2025-11-18
**Статус:** Спецификация для реализации
**Связанные документы:**
- [01_ARCHITECTURE_DECISIONS.md](./01_ARCHITECTURE_DECISIONS.md)
- [03_GRAPH_SCHEMA.md](./03_GRAPH_SCHEMA.md)

---

## Введение

Модели данных строго разделены:
1.  **Persistent Nodes:** То, что хранится в Neo4j (минималистично, без дублирования).
2.  **Workflow Structures:** Объекты Python/Pydantic для передачи данных внутри LangGraph и общения с фронтендом (богатые данными).

---

## 1. Persistent Graph Nodes (Neo4j)

### 1.1 PARA Containers (Контекст)
*Источники истины для структуры.*

```python
class Project(BaseModel):
    id: str = Field(..., description="UUID")
    name: str
    status: Literal["active", "completed", "archived"] = "active"
    deadline: Optional[datetime] = None

class Area(BaseModel):
    id: str = Field(..., description="UUID")
    name: str

class Resource(BaseModel):
    id: str = Field(..., description="UUID")
    name: str
```

### 1.2 Note (Точка входа)
*Представление файла.*
**Важно:** Здесь нет полей `project_id` или `para_type`. Принадлежность определяется только связью `[:IS_PART_OF]`.

```python
class Note(BaseModel):
    path: str = Field(..., description="Unique file path (Primary Key)")
    created_at: datetime
    updated_at: datetime
```

### 1.3 EntityNode (Смысл)
*Извлеченная информация.*
**Важно:** Здесь нет полей `status`. Статус определяется связью `[:HAS_CHECK]`.

```python
class EntityNode(BaseModel):
    uuid: str = Field(..., description="Unique ID")
    name: str
    # Strict Schema: только разрешенные типы
    labels: List[Literal["Concept", "Person", "Task", "Decision"]] 
    summary: Optional[str]
```

### 1.4 UserCheckStatus (История решений)
*Ключевая нода для Constructive Interaction.*
Хранит не просто "Да/Нет", а семантику выбора.

```python
class UserCheckStatus(BaseModel):
    id: str = Field(..., description="UUID")
    timestamp: datetime
    
    # Состояние процесса
    status: Literal["pending", "resolved"]
    
    # Результат (Outcome) - Что произошло?
    outcome: Literal[
        "confirmed_proposal",  # Согласился с системой
        "linked_alternative",  # Выбрал другое из списка/поиска
        "created_custom",      # Создал новое вручную
        "reclassified",        # Сменил тип (Project->Area)
        "dismissed",           # Отклонил (для сущностей)
        "auto_confirmed"       # Система решила сама
    ]
    
    # Snapshots (JSON strings) для аналитики "Было -> Стало"
    system_proposal_snapshot: Optional[str] 
    user_selection_snapshot: Optional[str]
    
    user_comment: Optional[str]
```

---

## 2. Workflow Structures (Internal State & API)

Эти модели используются в коде Python и для обмена данными с фронтендом (Obsidian Plugin).

### 2.1 PARA Proposal (L1 Output)
То, что система предлагает пользователю.

```python
class PARAProposal(BaseModel):
    """Гипотеза системы о том, куда привязать заметку."""
    primary_candidate: Dict[str, Any] # {id, name, type, confidence}
    alternatives: List[Dict[str, Any]] # Другие варианты с меньшим скором
    is_new_creation: bool # Предлагаем ли мы создать новый проект?
    reasoning: str # Почему LLM так решила (для UI)
```

### 2.2 User Decision Payload (Ответ Клиента)
То, что приходит от плагина через WebSocket при `interrupt`.

```python
class UserDecisionPayload(BaseModel):
    """Ответ пользователя на предложение системы."""
    check_id: str
    
    # Действие
    action: Literal[
        "confirm_proposal",
        "link_existing", # Пользователь выбрал ID из поиска
        "create_custom", # Пользователь ввел новое имя
        "dismiss"
    ]
    
    # Данные (заполняются в зависимости от action)
    target_id: Optional[str] = None       # UUID для link_existing
    new_name: Optional[str] = None        # Name для create_custom
    new_type: Optional[str] = None        # Type для create_custom
    comment: Optional[str] = None
```

### 2.3 Extracted Candidate (L3 Output)
Сущность-кандидат до сохранения в базу.

```python
class ExtractedCandidate(BaseModel):
    """Сырой результат от Graphiti с контекстом."""
    name: str
    label: str
    summary: str
    confidence: float
    context_source: str # Название проекта, в рамках которого извлечено
```

---

## 3. Константы Конфигурации

```python
# Разрешенные типы для Graphiti (Whitelist)
ALLOWED_ENTITY_LABELS = [
    "Concept", 
    "Person", 
    "Task", 
    "Decision"
]

# Пороги уверенности
CONFIDENCE_THRESHOLDS = {
    "auto_link_project": 0.90,    # Если > 90%, линкуем без вопроса
    "auto_confirm_task": 0.95,    # Если Task > 95%, сохраняем молча
    "ask_user": 0.0               # Иначе спрашиваем
}
```

---

**Навигация:** **← Предыдущий** [01_ARCHITECTURE_DECISIONS.md](./01_ARCHITECTURE_DECISIONS.md) | **Следующий →** [03_GRAPH_SCHEMA.md](./03_GRAPH_SCHEMA.md)