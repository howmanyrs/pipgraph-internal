Вот обновленная версия `04_LANGGRAPH_WORKFLOW_v03.md`.

**Ключевые изменения:**
1.  **User Decision Model:** Вместо простого `Confirm/Reject` узел обработки ответа теперь умеет обрабатывать `Link Alternative`, `Create Custom` и `Reclassify`.
2.  **State Management:** Добавлены поля для хранения "сырого" выбора пользователя перед коммитом.
3.  **Strict Sequence:** Четкое разделение на Phase 1 (Linking) и Phase 2 (Extraction) с двумя разными точками записи (Commit).

---
--- START OF FILE 04_LANGGRAPH_WORKFLOW_V3.md ---

# LangGraph Workflow V3: Constructive Interaction

**Дата обновления:** 2025-11-18
**Статус:** Implementation Guide
**Версия:** 3.0
**Связанные документы:** [06_USER_INTERACTION_REQUIREMENTS.md](./06_USER_INTERACTION_REQUIREMENTS.md)

---

## 1. Логика Workflow

Workflow построен на принципе **"Предлагай, а не спрашивай"**. Система выдвигает гипотезу (например, "Это Проект X"), а пользователь либо подтверждает её, либо конструктивно меняет ("Нет, это Область Y").

```mermaid
graph TB
    START([START]) --> l1_identify[**L1 Identify**<br/>LLM: Find best PARA match]

    l1_identify --> check_conf{High Confidence?}
    
    check_conf -- No --> ask_para[🔴 INTERRUPT<br/>"Link to Project X or Choose Other?"]
    check_conf -- Yes --> auto_link[Set Proposal as Choice]

    ask_para --> process_decision[**Process Decision**<br/>Handle: Confirm / Link Other / Create]
    auto_link --> commit_link
    process_decision --> commit_link
    
    commit_link[**COMMIT 1**<br/>Create [:IS_PART_OF]] --> l3_extract
    
    l3_extract[**L3 Extract**<br/>Graphiti + Context] --> l3_check{Found Entities?}
    
    l3_check -- Yes --> ask_entities[🔴 INTERRUPT<br/>"Confirm / Edit / Dismiss"]
    l3_check -- No --> finalize
    
    ask_entities --> process_entities[**Process Entities**<br/>Save Confirmed, Drop Dismissed]
    
    process_entities --> finalize[**COMMIT 2**<br/>Save Entity Nodes] --> END([END])

    style ask_para fill:#fff3cd
    style ask_entities fill:#fff3cd
    style commit_link fill:#d1e7dd,stroke:#0f5132
    style finalize fill:#d1e7dd,stroke:#0f5132
```

---

## 2. NoteWorkflowState (TypedDict)

Состояние теперь включает поля для обработки сложного выбора пользователя.

```python
class NoteWorkflowState(TypedDict):
    # --- Input ---
    file_path: str
    content: str
    
    # --- L1/L2: Context Phase ---
    # Что предложила система (для UI)
    system_proposal: Optional[Dict]  # {type: "Project", name: "New Web", reason: "..."}
    
    # Что в итоге выбрал пользователь (или авто-выбор)
    final_context: Optional[Dict]    # {id: "uuid", type: "Area", name: "Design"}
    
    # --- L3: Content Phase ---
    extracted_candidates: List[Dict] # Список найденных сущностей
    
    # --- Interaction ---
    user_decision_payload: Optional[Dict] # JSON ответ от клиента (Obsidian)
```

---

## 3. Реализация Узлов (Nodes)

### Node 1: `identify_context_node` (L1)

Пытается найти существующий проект или предлагает создать новый.

```python
async def identify_context_node(state: NoteWorkflowState) -> dict:
    pipgraph = await get_pipgraph_manager()
    
    # LLM анализирует текст и ищет совпадения в базе Projects/Areas
    proposal, confidence = await pipgraph.identify_best_para_match(state["content"])
    
    # Если уверенность высокая -> сразу готовим к линковке
    # Если низкая -> отправляем на Interrupt
    return {
        "system_proposal": proposal,
        "processing_stage": "l1_identification"
    }
```

### Node 2: `process_context_decision_node`

Разбирает сложный ответ пользователя ("Нет, это не Проект А, привяжи к Области Б").

```python
async def process_context_decision_node(state: NoteWorkflowState) -> dict:
    decision = state["user_decision_payload"] # Пришло от клиента
    pipgraph = await get_pipgraph_manager()
    
    final_context = None
    
    if decision["action"] == "confirm_proposal":
        final_context = state["system_proposal"]
        
    elif decision["action"] == "link_existing":
        # Пользователь выбрал другой контейнер из поиска
        final_context = await pipgraph.get_container(decision["target_id"])
        
    elif decision["action"] == "create_custom":
        # Пользователь ввел новое имя
        new_id = await pipgraph.create_para_container(
            type=decision["new_type"], 
            name=decision["new_name"]
        )
        final_context = {"id": new_id, "type": decision["new_type"], ...}
        
    # Сохраняем выбор в историю (UserCheckStatus)
    await pipgraph.save_context_check_status(
        note_path=state["file_path"],
        outcome=decision["action"],
        system_proposal=state["system_proposal"],
        user_selection=final_context
    )
        
    return {"final_context": final_context}
```

### Node 3: `commit_link_node` (Commit 1)

Физически создает связь. Это точка невозврата для L1/L2.

```python
async def commit_link_node(state: NoteWorkflowState) -> dict:
    pipgraph = await get_pipgraph_manager()
    ctx = state["final_context"]
    
    # Создает ребро [:IS_PART_OF]
    await pipgraph.link_note_to_container(
        note_path=state["file_path"],
        container_id=ctx["id"]
    )
    return {"processing_stage": "l2_linked"}
```

### Node 4: `extract_content_node` (L3)

Запускает Graphiti с инъекцией контекста.

```python
async def extract_content_node(state: NoteWorkflowState) -> dict:
    pipgraph = await get_pipgraph_manager()
    ctx = state["final_context"]
    
    # "Context: This note belongs to Project 'Rebranding'..."
    entities = await pipgraph.extract_entities_with_context(
        content=state["content"],
        context_name=ctx["name"],
        context_type=ctx["type"]
    )
    
    return {"extracted_candidates": entities}
```

---

## 4. Условные переходы (Conditional Edges)

### `should_interrupt_context`
Решает, нужно ли беспокоить пользователя на этапе L1.

```python
def should_interrupt_context(state: NoteWorkflowState):
    # Если LLM не уверена или нашла несколько кандидатов
    if state["system_proposal"]["confidence"] < 0.85:
        return "ask_para"
    return "auto_link" # Skip UI, go to commit
```

### `should_interrupt_content`
Решает, есть ли важные сущности для подтверждения.

```python
def should_interrupt_content(state: NoteWorkflowState):
    candidates = state["extracted_candidates"]
    if not candidates:
        return "finalize"
        
    # Фильтр: показываем только High Priority (Person, Concept)
    # Low Priority (Task) можно авто-подтверждать, если confidence > 0.9
    return "ask_entities"
```

---

## 5. Что получает Frontend (Obsidian)?

При прерывании (`interrupt`) фронтенд получает не просто текст вопроса, а **Actionable Object**:

```json
// Пример payload для L1 Interrupt
{
  "type": "context_confirmation",
  "note_path": "meetings/2025-11-18.md",
  "proposal": {
    "type": "Project",
    "name": "Website Redesign",
    "reason": "Mentioned deadlines and design tasks"
  },
  "alternatives": [
    {"type": "Area", "name": "Design General", "confidence": 0.3}
  ]
}
```

Это позволяет плагину отрисовать красивый UI с кнопками "Подтвердить Project" или "Выбрать Area".

---

**Следующий документ:** [05_IMPLEMENTATION_ROADMAP_V3.md](./05_IMPLEMENTATION_ROADMAP_V3.md)