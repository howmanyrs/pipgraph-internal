# MVP Scope - Границы минимальной версии

**Цель:** Определить, что ВХОДИТ и что НЕ ВХОДИТ в MVP, учитывая архитектуру на основе детализированных связей.

---

## Определение MVP

**MVP = Минимальная версия, которая демонстрирует работоспособность архитектуры:**
- **Top-Down подход** (L1/L2 → L3)
- **No-Cache Policy** (граф как источник истины, отсутствие дублирующих полей в узлах)
- **State in Relationships** (состояние определяется типом и атрибутами связей)
- **Granular Suggestions** (система может предлагать несколько действий одновременно: связать, переименовать, уточнить описание)
- **Constructive Interaction** (нет тупиков: заметка всегда привязана к PARA контейнеру)

**НЕ MVP = Продакшн-готовая система со всеми edge cases.**

---

## Must-Have для MVP ✅

### 1. Database Layer
- **Neo4j схема** с узлами: `Project`, `Area`, `Resource`, `Episodic`, `Entity`
- **Базовые индексы:** `Episodic.name` (unique), `Project.id`, `Entity.uuid`, `SUGGESTS.suggestion_id`
- **Связи (Relationships):**
  - `:IS_PART_OF` (Факт: утвержденная связь заметки с контейнером)
  - `:SUGGESTS` (Гипотеза: предложение системы). **Множественность:** между двумя узлами может быть несколько ребер с разными `suggestion_id` и типами (`link`, `property_update`).
  - `:MENTIONS` (Содержание: связь с извлеченной сущностью)
- **CRUD операции:** создание/чтение PARA контейнеров, управление Episodic узлами.
- **Атомарное управление связями:** создание и удаление конкретных ребер по `suggestion_id`.

### 2. L1/L2 PARA Identification
- **Классификация PARA типа** через LLM (Project/Area/Resource)
- **Поиск похожих контейнеров** по embeddings
- **Генерация комплексного предложения** (Proposal):
  - Может содержать предложение о связи (`link`).
  - Может содержать предложение об обновлении свойств (`property_update`, например, переименование проекта).
- **Запись в граф:** создание одного или нескольких ребер `:SUGGESTS` с уникальными UUID.
- **Обработка решения пользователя:**
  - **Confirm Link:** Трансформация `:SUGGESTS` → `:IS_PART_OF`.
  - **Confirm Update:** Обновление свойства целевого узла, удаление ребра `:SUGGESTS`.
  - **Link to alternative:** Удаление всех `:SUGGESTS`, создание `:IS_PART_OF` к выбранному контейнеру.
  - **Create custom:** Создание нового узла, удаление `:SUGGESTS`, создание `:IS_PART_OF`.
  - **Dismiss:** Удаление конкретного ребра `:SUGGESTS` (fallback to Inbox, если удалено последнее предложение о связи).

### 3. User Interaction Flow
- **Interrupt Loop:** LangGraph ставит процесс на паузу, пока в графе существует *хотя бы одна* связь `:SUGGESTS` для данной заметки.
- **Iterative Decision:** Пользователь может последовательно подтвердить связь, а затем подтвердить (или отклонить) переименование.
- **JSON payload:** Фронтенд получает список всех активных предложений с их ID и типами.

### 4. L3 Context-Aware Extraction
- **Context injection** в Graphiti промпт (имя PARA контейнера берется из связи `:IS_PART_OF`)
- **Schema whitelist** для типов сущностей: `Concept`, `Person`, `Task`, `Decision`
- **Batch save** извлеченных сущностей в граф (создание узлов `Entity`)
- **Создание связей** `(Episodic)-[:MENTIONS {status: "confirmed"}]->(Entity)`

### 5. Graph Traversal
- **Get PARA context** для episodic: `MATCH (e:Episodic)-[:IS_PART_OF]->(container) RETURN container`
- **Get suggestions:** Поиск всех ребер `:SUGGESTS` для отображения в UI.

### 6. Testing
- **Unit тесты** для логики генерации Proposal.
- **Integration тесты** с реальным Neo4j (проверка создания множественных связей и их независимого удаления).
- **E2E тест** полного цикла с пошаговым подтверждением решений.

---

## Can Defer (Откладываем) ⏳

### 1. Rich History & Audit
**В MVP:**
- История изменений не сохраняется.
- При отказе от `:SUGGESTS` связь просто удаляется.

**Откладываем:**
- Узлы `UserCheckStatus` для хранения истории решений.
- Аналитика "Какие проекты чаще всего переименовываются AI".

### 2. Advanced Entity Management
**В MVP:**
- Сохранение сущностей как есть.
- Удаление сущности = удаление связи `:MENTIONS`.

**Откладываем:**
- Merge дубликатов сущностей.
- Ручное редактирование свойств сущности через UI.

### 3. Duplicate Detection
**В MVP:**
- Нет проверки на дубликаты заметок по контенту (только по `path`).

### 4. Reclassification Workflow
**В MVP:**
- Episodic привязывается к PARA контейнеру один раз. Изменение возможно только прямым вмешательством в БД.

---

## Technical Simplifications (Упрощения)

### 1. Auto-Confirmation Thresholds
**В MVP:**
- High bars для auto-link: **>95% confidence**.
- Property Updates (переименование) **всегда** создаются как `:SUGGESTS` и требуют подтверждения (safety first).

### 2. State Management via Relationships
**В MVP:**
- Состояние "Требует внимания" = `EXISTS( (n)-[:SUGGESTS]->() )`.
- Состояние "Готово к экстракции" = `NOT EXISTS( :SUGGESTS ) AND EXISTS( :IS_PART_OF )`.

### 3. Error Handling
**В MVP:**
- Если пользователь отклонил все предложения и не выбрал альтернативу -> Auto-link to **Inbox**.

---

## Definition of Done (Критерии готовности MVP)

### Функциональные критерии
1. ✅ **Happy path (Simple Link):**
   - AI создает `:SUGGESTS` (link) → User confirms → Transform to `:IS_PART_OF` → L3 Extraction.

2. ✅ **Complex path (Link + Update):**
   - AI создает 2 ребра `:SUGGESTS` → User confirms Link → User confirms Update (Project renamed) → L3 Extraction (with new name).

3. ✅ **Alternative/Custom path:**
   - User selects alternative → Old suggestions deleted → New context created.

4. ✅ **No-Cache проверка:**
   - В `Episodic` узле нет поля `project_id`.
   - Вся информация достается через traversal связей.

### Технические критерии
1. ✅ **Unit тесты покрывают ≥80% методов** `PipGraphManager`.
2. ✅ **Integration тесты проверяют** операции с `suggestion_id` (удаление конкретного ребра из множества).
3. ✅ **E2E тест проходит** для сценария с прерыванием.
4. ✅ **Чистота графа:** нет "висячих" узлов, все suggestions обработаны.

---

## Risks & Mitigation (Риски MVP)

### Risk 1: User Fatigue
**Проблема:** Слишком много предложений (link, rename, summary update) для каждой заметки.
**Mitigation:** В MVP ограничиваемся типами `link` и `property_update` (только для имени). Summary update откладываем.

---

## Next Steps

После прочтения этого документа переходите к:
- **[02_IMPLEMENTATION_STEPS.md](./02_IMPLEMENTATION_STEPS.md)** для пошагового плана реализации.
- **[03_DATA_STRUCTURES.md](./03_DATA_STRUCTURES.md)** для моделей данных.

**Помните:** Цель MVP — доказать гибкость архитектуры связей, способной обрабатывать сложные сценарии (как переименование) без усложнения схемы узлов.