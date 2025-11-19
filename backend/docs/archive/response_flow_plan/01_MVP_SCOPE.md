# MVP Scope - Границы минимальной версии

**Цель:** Определить, что ВХОДИТ и что НЕ ВХОДИТ в MVP, чтобы не запутаться в излишних деталях.

---

## Определение MVP

**MVP = Минимальная версия, которая демонстрирует работоспособность архитектуры:**
- Top-Down подход (L1/L2 → L3)
- No-Cache Policy (граф как источник истины)
- Constructive Interaction (нет тупиков)

**НЕ MVP = Продакшн-готовая система со всеми edge cases.**

---

## Must-Have для MVP ✅

### 1. Database Layer
- **Neo4j схема** с узлами: `Project`, `Area`, `Resource`, `Episodic`, `Entity`, `UserCheckStatus`
- **Базовые индексы:** `Episodic.path` (unique), `Project.id`, `Area.id`, `Resource.id`
- **Связи:** `:IS_PART_OF`, `:MENTIONS`, `:HAS_CHECK`
- **CRUD операции:** создание/чтение PARA контейнеров, создание/обновление episodic узлов

### 2. L1/L2 PARA Identification
- **Классификация PARA типа** через LLM (Project/Area/Resource)
- **Поиск похожих контейнеров** по embeddings (топ-3 кандидата)
- **Генерация предложения** (`PARAProposal` с primary + alternatives)
- **Обработка решения пользователя:**
  - Confirm → link episodic to primary
  - Link to alternative → link episodic to selected container
  - Create new → create container + link episodic

### 3. User Interaction Flow
- **Interrupt механизм** (LangGraph pause на `UserCheckStatus` узле)
- **JSON payload для фронтенда** с actionable опциями
- **Parsing user decision** из WebSocket response
- **Resume workflow** после получения решения

### 4. L3 Context-Aware Extraction
- **Context injection** в Graphiti промпт (имя проекта)
- **Schema whitelist** для типов сущностей: `Concept`, `Person`, `Task`, `Decision`
- **Batch save** извлеченных сущностей в граф
- **Создание связей** `(Episodic)-[:MENTIONS]->(Entity)`

### 5. Graph Traversal
- **Get PARA context** для episodic: `get_episodic_para_context(episodic_path) → Project/Area/Resource`
- **Get entity status** для сущности: `get_entity_current_status(entity_uuid) → UserCheckStatus`
- **Traversal через связи**, НЕ через атрибуты узлов

### 6. Testing
- **Unit тесты** для каждого метода PipGraphManager
- **Integration тесты** с реальным Neo4j (testcontainers или локальный)
- **Mocked LLM вызовы** для предсказуемости тестов
- **E2E тест** полного цикла (episodic → identification → extraction → graph check)

---

## Can Defer (Откладываем) ⏳

### 1. UserCheckStatus - Rich History
**В MVP:**
- Храним только: `id`, `timestamp`, `status`, `outcome`, `comment`
- Outcome = простая строка (`"confirmed"`, `"linked_to_alternative"`, `"created_custom"`)

**Откладываем:**
- Полные снапшоты `system_proposal_snapshot`, `user_selection_snapshot`
- Построение цепочки `[:NEXT]` для анализа истории решений
- UI для просмотра истории изменений

### 2. Advanced Analytics
**В MVP:**
- Просто сохраняем решения в `UserCheckStatus`

**Откладываем:**
- Аналитика: "Какие проекты чаще reject?"
- Метрики: "Среднее время на принятие решения"
- Dashboard для review прошлых решений

### 3. Entity Management UI
**В MVP:**
- Базовые операции: `modify_entity()`, `reject_entity()`
- Простая логика: modify = update name/summary, reject = delete node

**Откладываем:**
- Merge дубликатов
- Split сущности на части
- Reclassification (Task → Decision)

### 4. Multi-Round Extraction
**В MVP:**
- Один проход извлечения → confirmation → save

**Откладываем:**
- Iterative refinement (user reject → LLM retry)
- Partial save (сохранить confirmed, переспросить rejected)

### 5. Duplicate Detection
**В MVP:**
- Нет проверки на дубликаты заметок

**Откладываем:**
- SHA-256 hash для content
- Проверка при создании: "Эта заметка уже обработана?"

### 6. Reclassification Workflow
**В MVP:**
- Episodic привязан к одному PARA контейнеру навсегда (пока не изменим вручную в Neo4j)

**Откладываем:**
- UI кнопка "Move to another Project/Area"
- Workflow для переклассификации с сохранением истории

### 7. Advanced Graphiti Features
**В MVP:**
- Простой context injection: `f"Context: Project '{project_name}'"`
- Базовый whitelist типов

**Откладываем:**
- Custom facts extraction rules
- Temporal reasoning (even happened before/after)
- Cross-note entity resolution

---

## Technical Simplifications (Упрощения)

### 1. Auto-Confirmation Thresholds
**В MVP:**
- High bars для auto-link: **>95% confidence**
- Почти всегда спрашиваем пользователя

**Почему:**
- Избегаем ошибочных привязок
- Лучше больше interrupts, чем неправильная классификация

**Потом:**
- Понизить порог до 85-90% после накопления статистики

### 2. UserCheckStatus Snapshots
**В MVP:**
- Snapshot = простой dict с 2-3 полями:
  ```python
  {
    "primary_candidate": "Project X",
    "user_selection": "Project X",
    "action": "confirmed"
  }
  ```

**Почему:**
- Не нужна полная копия всех полей для MVP
- Упрощает логику сохранения

**Потом:**
- Добавить full proposal diff для анализа

### 3. Error Handling
**В MVP:**
- Базовая обработка: try/except + логирование
- Workflow падает → пользователь видит ошибку

**Почему:**
- Не тратим время на retry логику, circuit breakers

**Потом:**
- Retry для LLM вызовов
- Graceful degradation (если Graphiti упал → пропустить L3)

### 4. Performance Optimization
**В MVP:**
- Нет кэширования embeddings
- Нет batch processing заметок
- Sequential обработка

**Почему:**
- Фокус на корректности, не на скорости

**Потом:**
- Кэш embeddings в Redis
- Batch обработка для импорта vault

---

## Definition of Done (Критерии готовности MVP)

### Функциональные критерии
1. ✅ **Happy path работает:**
   - Episodic → L1/L2 → User confirms → L3 → Entities saved
   - Граф содержит правильные связи `[:IS_PART_OF]`, `[:MENTIONS]`

2. ✅ **Alternative path работает:**
   - Episodic → L1/L2 → User selects alternative → Link to chosen container
   - Система не создает "сирот" (episodic without PARA link)

3. ✅ **Create custom path работает:**
   - Episodic → L1/L2 → User creates new Project → Link to new container

4. ✅ **Context injection работает:**
   - Graphiti получает project name в промпте
   - Извлечение зависит от контекста (проверяем в логах)

5. ✅ **No-Cache проверка:**
   - В `Episodic` узле нет поля `project_id`
   - В `Entity` узле нет поля `status`
   - Вся информация достается через traversal

### Технические критерии
1. ✅ **Unit тесты покрывают ≥80% методов** PipGraphManager
2. ✅ **Integration тесты проверяют** граф-операции (создание узлов, связей)
3. ✅ **E2E тест проходит** для полного цикла (≥1 сценарий)
4. ✅ **Mocked LLM работает** в тестах (нет реальных API вызовов в unit)
5. ✅ **Логирование настроено** (можно отследить workflow execution)

### Качественные критерии
1. ✅ **Код читаем:** методы <50 строк, понятные имена
2. ✅ **Архитектура соблюдена:** API → Service → CRUD → Neo4j
3. ✅ **Нет hardcoded значений:** все конфиги в `.env` или constants
4. ✅ **Docstrings для публичных методов** PipGraphManager

---

## Out of Scope (Точно НЕ делаем)

❌ **Frontend UI** (плагин Obsidian) — это отдельный проект
❌ **WebSocket сервер** — фокус на backend логике, API endpoints можно замокать
❌ **Multi-user support** — MVP для одного пользователя
❌ **Permissions & Auth** — нет разграничения прав
❌ **Backup & Recovery** — ручная работа с Neo4j dump
❌ **Production deployment** — Docker Compose для локальной разработки

---

## Risks & Mitigation (Риски MVP)

### Risk 1: LLM API Costs
**Проблема:** Много вызовов к OpenRouter для тестов
**Mitigation:** Используем mock в unit тестах, реальный LLM только в integration (mark `@pytest.mark.llm`)

### Risk 2: Neo4j Schema Changes
**Проблема:** Изменение схемы может сломать существующий граф
**Mitigation:** Используем тестовый Neo4j контейнер, не трогаем production

### Risk 3: Graphiti Integration Complexity
**Проблема:** Graphiti может работать не так, как ожидаем
**Mitigation:** Iteration 4 полностью посвящена Graphiti, проверяем assumptions рано

### Risk 4: Interrupt/Resume Logic
**Проблема:** LangGraph interrupts могут быть сложными
**Mitigation:** Iteration 3 фокусируется только на interrupt flow, тестируем изолированно

---

## Next Steps

После прочтения этого документа переходите к:
- **[02_IMPLEMENTATION_STEPS.md](./02_IMPLEMENTATION_STEPS.md)** для пошагового плана
- **[03_DATA_STRUCTURES.md](./03_DATA_STRUCTURES.md)** для моделей

**Помните:** Цель MVP — доказать, что архитектура работает, а не построить идеальную систему.
