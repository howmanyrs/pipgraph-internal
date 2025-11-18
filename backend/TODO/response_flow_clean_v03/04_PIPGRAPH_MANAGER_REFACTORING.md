# PipGraphManager Refactoring: Architecture Analysis

**Дата обновления:** 2025-11-18
**Статус:** Architectural Guide

---

## Executive Summary

### Смена парадигмы: "Контекст превыше всего"

Мы отказываемся от попытки "сделать всё сразу" и от хранения избыточных данных.
Архитектура PipGraphManager меняется с монолитной обработки на набор узкоспециализированных инструментов, которые LangGraph вызывает в строгой последовательности: **Сначала PARA (L1/L2), потом Сущности (L3).**

### Ключевые изменения

1.  **No-Cache Policy (Отказ от кэширования):**
    *   Мы больше **не храним** `para_type`, `project_id` или `check_status` внутри нод `Note` или `EntityNode`.
    *   **Источник истины — связи.** Если нужно узнать проект заметки, мы делаем запрос `(Note)-[:IS_PART_OF]->(Project)`.
    *   **Результат:** Удалены методы синхронизации атрибутов. Код записи стал проще и надежнее.

2.  **Context-Aware Extraction (Умное извлечение):**
    *   Мы не запускаем Graphiti "вслепую".
    *   Сначала определяем Проект/Область.
    *   Передаем этот контекст в Graphiti и жестко ограничиваем типы сущностей (Schema Constraints), чтобы избежать создания мусорных нод.

---

## 1. Новая структура методов (API)

Вместо одного метода `process_note`, менеджер теперь предоставляет набор атомарных операций.

### Группа 1: PARA Management (L1 & L2)
*Эти методы вызываются первыми.*

1.  `classify_note_para(content) -> (type, confidence)`
    *   LLM-запрос для определения типа (Project, Area, Resource).
2.  `find_similar_containers(content, type) -> candidates`
    *   Поиск существующих проектов/областей через embeddings.
3.  `create_para_container(type, name, metadata) -> container_id`
    *   Создание новой ноды Project/Area/Resource.
4.  `link_note_to_container(note_path, container_id) -> bool`
    *   **Критически важно:** Создает только связь `[:IS_PART_OF]`. Не меняет атрибуты заметки.

### Группа 2: Context-Aware Extraction (L3)
*Вызываются только после того, как заметка привязана к контейнеру.*

5.  `extract_entities_with_context(content, container_context) -> entities`
    *   **Новая сигнатура:** Принимает название проекта/области как контекст.
    *   **Strict Schema:** Использует whitelist типов (Concept, Person, Task), игнорируя остальные.
6.  `save_entity_check(entity_uuid, status) -> check_id`
    *   Создает `UserCheckStatus` и линкует его к сущности.
7.  `modify_entity(entity_uuid, changes)`
    *   Прямое изменение атрибутов сущности в Neo4j.
8.  `reject_entity(entity_uuid)`
    *   Помечает сущность как отклоненную (через статус).

### Группа 3: Graph Traversal (Getters)
*Замена кэшированным атрибутам. Методы читают состояние из графа.*

9.  `get_note_para_context(note_path) -> container_node`
    *   Находит, к какому проекту привязана заметка (через `[:IS_PART_OF]`).
10. `get_entity_current_status(entity_uuid) -> status`
    *   Находит текущий статус сущности (через `[:HAS_CHECK {is_current:true}]`).

---

## 2. Детальная спецификация методов

### 2.1 PARA Operations (L1/L2)

```python
async def classify_note_para(self, content: str) -> tuple[str, float]:
    """
    L1: Определяет тип заметки (Project, Area, Resource, Archive).
    Использует LLM с простым промптом классификации.
    """
    # Implementation: LLM call
    pass

async def link_note_to_container(
    self, 
    note_path: str, 
    container_id: str
) -> bool:
    """
    L2: Создает жесткую связь между заметкой и контейнером.
    
    Принцип No-Cache: Мы НЕ пишем container_id внутрь Note.
    Мы создаем ребро.
    """
    query = """
    MATCH (n:Note {path: $note_path})
    MATCH (c {id: $container_id}) -- Ищем среди Project/Area/Resource
    MERGE (n)-[r:IS_PART_OF]->(c)
    SET r.assigned_at = datetime()
    """
    # Implementation: Run Cypher
    pass
```

### 2.2 Context-Aware Extraction (L3)

```python
async def extract_entities_with_context(
    self,
    note_content: str,
    note_path: str,
    container_info: dict = None  # {"name": "Website Launch", "type": "Project"}
) -> tuple[List[EntityNode], str]:
    """
    L3: Извлекает сущности, используя контекст PARA.
    
    Особенности:
    1. Промпт включает: "Эта заметка относится к проекту '{name}'".
    2. Schema Constraints: Разрешаем только ['Person', 'Organization', 'Concept', 'Task'].
       Запрещаем Graphiti создавать гранулярный шум.
    """
    
    # 1. Формируем строгий конфиг для Graphiti
    schema_config = {
        "allowed_labels": ["Person", "Organization", "Concept", "Task"],
        # Запрещаем Graphiti выдумывать типы
    }
    
    # 2. Формируем контекстный промпт
    context_str = ""
    if container_info:
        context_str = f"Context: This note belongs to {container_info['type']} '{container_info['name']}'."
    
    # 3. Вызываем Graphiti (но пока НЕ сохраняем связи в базу, возвращаем объекты)
    # ...
    pass
```

### 2.3 Status Management

```python
async def save_entity_check(
    self,
    entity_uuid: str,
    status: str, # "confirmed", "rejected"
    user_comment: Optional[str] = None
) -> str:
    """
    Создает ноду UserCheckStatus.
    
    Simplified MVP:
    - Не сохраняем сложную историю изменений полей (diffs).
    - Просто фиксируем факт: "Юзер сказал ОК" или "Юзер сказал НЕТ".
    """
    query = """
    MATCH (e:EntityNode {uuid: $entity_uuid})
    
    // 1. Снимаем флаг is_current с предыдущего статуса (если был)
    OPTIONAL MATCH (e)-[old_rel:HAS_CHECK]->(old_check)
    WHERE old_rel.is_current = true
    SET old_rel.is_current = false
    
    // 2. Создаем новый статус
    CREATE (new_check:UserCheckStatus {
        id: randomUUID(),
        status: $status,
        timestamp: datetime(),
        comment: $comment
    })
    
    // 3. Линкуем
    CREATE (e)-[:HAS_CHECK {is_current: true}]->(new_check)
    
    // 4. (Опционально) Цепочка истории
    WITH new_check, old_check
    WHERE old_check IS NOT NULL
    CREATE (new_check)-[:NEXT]->(old_check)
    
    RETURN new_check.id
    """
    pass
```

---

## 3. Сравнение: Старый vs Новый подход

| Характеристика | Legacy подход | Новая архитектура |
| :--- | :--- | :--- |
| **Порядок** | Extract -> Classify | **Classify (PARA) -> Extract** |
| **Хранение данных** | Атрибуты `project_id` в Note | **Только связь `[:IS_PART_OF]`** |
| **Извлечение (L3)** | Generic (все подряд) | **Context-Aware (Project name)** |
| **Гранулярность** | Высокая (шум) | **Строгая схема (Concept/Task)** |
| **Методы** | 17 методов (много сеттеров) | **~10 методов (Focus on Links)** |
| **User History** | Complex field diffs | **Simple Status (Confirmed/Rejected)** |

---

## 4. План рефакторинга

### День 1: PARA Backbone (L1/L2)
1.  Реализовать `classify_note_para` (LLM).
2.  Реализовать `create_para_container` и `find_similar_containers`.
3.  Реализовать `link_note_to_container` (чистый Cypher).
4.  *Тест:* Заметка классифицируется и линкуется к Проекту. Сущности пока игнорируем.

### День 2: Context Extraction (L3)
1.  Реализовать `extract_entities_with_context`.
    *   Настроить Graphiti `schema` (whitelist).
    *   Интегрировать контекст в промпт.
2.  Реализовать `save_entity_check` (UserCheckStatus).
3.  Реализовать `bulk_save_graph` (Финальное сохранение подтвержденных сущностей).

### День 3: Интеграция и Чистка
1.  Удалить старый код, связанный с обновлением атрибутов (`update_note_para_type`).
2.  Проверить E2E на тестовой заметке:
    *   Note -> L1 (Project) -> L2 (Link) -> L3 (Extract "Concept") -> Save.

---

**Навигация:** **← Предыдущий** [03_GRAPH_SCHEMA.md](./03_GRAPH_SCHEMA.md) | **Следующий →** [05_LANGGRAPH_WORKFLOW.md](./05_LANGGRAPH_WORKFLOW.md)