# PipGraph Backend Test Suite

Комплексная система тестирования бэкенда с разделением по типам и уровням интеграции.

## Содержание

- [Быстрый старт](#быстрый-старт)
- [Структура тестов](#структура-тестов)
- [Типы тестов](#типы-тестов)
- [Запуск тестов](#запуск-тестов)
- [Фикстуры](#фикстуры)
- [Маркеры](#маркеры)
- [Лучшие практики](#лучшие-практики)

---

## Быстрый старт

### Установка зависимостей

```bash
# Перейдите в директорию backend
cd backend/

# Активируйте виртуальное окружение
source .venv/bin/activate  # Linux/macOS
# .\.venv\Scripts\activate  # Windows

# Установите тестовые зависимости
uv pip install -r requirements-dev.txt
```

### Запуск всех тестов

```bash
pytest
```

### Запуск только быстрых тестов

```bash
pytest -m unit
```

---

## Структура тестов

```
tests/
├── conftest.py                 # Общие фикстуры и конфигурация
│
├── unit/                       # Unit-тесты (быстрые, изолированные)
│   ├── __init__.py
│   └── test_models.py          # Тесты Pydantic моделей
│
├── integration/                     # Integration-тесты (с внешними сервисами)
│   ├── __init__.py
│   ├── test_neo4j.py               # Тесты подключения к Neo4j
│   ├── test_openai_generic_config.py # Тесты LLM через OpenAI-compatible API (Cloud.ru)
│   └── test_note_processor.py      # Тесты обработки заметок с Graphiti
│
└── e2e/                        # End-to-end тесты (полный flow)
    └── __init__.py
```

---

## Типы тестов

### 1. Unit Tests (`unit/`)

**Назначение:** Быстрые изолированные тесты без внешних зависимостей

**Характеристики:**
- ⚡ Очень быстрые (миллисекунды)
- 🔒 Изолированные (без БД, API, файловой системы)
- 🎯 Тестируют отдельные функции/классы
- 🤖 Используют моки для внешних зависимостей

**Примеры:**
```python
# tests/unit/test_models.py
@pytest.mark.unit
def test_note_payload_creation():
    """Тест создания модели NotePayload"""
    note = NotePayload(
        file_path="test/note.md",
        content="Test content"
    )
    assert note.file_path == "test/note.md"
```

**Когда использовать:**
- Тестирование Pydantic моделей
- Валидация бизнес-логики без IO
- Утилитарные функции
- Парсеры, валидаторы

---

### 2. Integration Tests (`integration/`)

**Назначение:** Тесты взаимодействия с внешними сервисами

**Характеристики:**
- 🐢 Медленнее unit-тестов (секунды)
- 🔌 Требуют реальные сервисы (Neo4j, OpenRouter)
- 🔗 Тестируют интеграцию компонентов
- 💰 Могут расходовать API-кредиты (OpenRouter)

**Примеры:**

#### Neo4j (`test_neo4j.py`)
```python
@pytest.mark.integration
def test_neo4j_connection_with_fixture(neo4j_session):
    """Тест подключения к Neo4j через фикстуру"""
    result = neo4j_session.run("RETURN 1 as num")
    assert result.single()["num"] == 1
```

#### OpenAI-Compatible LLM Provider (`test_openai_generic_config.py`)
```python
@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.asyncio
@pytest.mark.parametrize("model_name", [
    pytest.param("small", id="small_model"),
    pytest.param("main", id="main_model"),
])
async def test_llm_chat_completion(model_name):
    """Тест базового LLM-запроса через OpenAI-compatible API (Cloud.ru)"""
    # Проверяет реальный API-вызов с параметризацией моделей
```

#### Note Processing (`test_note_processor.py`)
```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_process_person_note():
    """Тест обработки заметки о человеке"""
    note = NotePayload(
        file_path="notes/people/john_doe.md",
        content="John Doe is a software engineer..."
    )
    result = await process_and_store_note(note)
    assert result.nodes is not None
```

**Когда использовать:**
- Проверка подключения к БД
- Тестирование CRUD-операций
- Проверка LLM API (Cloud.ru, OpenAI-compatible providers)
- Интеграция с Graphiti
- Тестирование embeddings моделей

---

### 3. End-to-End Tests (`e2e/`)

**Назначение:** Тесты полного пользовательского сценария

**Характеристики:**
- 🐌 Самые медленные (секунды-минуты)
- 🎭 Симулируют реальное использование
- 🔄 Тестируют весь стек (API → Service → CRUD → DB)
- 🎯 Фокус на бизнес-сценариях

**Примеры будущих тестов:**
- WebSocket-соединение для обработки заметки
- Полный цикл: загрузка → обработка → сохранение → поиск
- Multi-note processing с связями
- Obsidian feedback cycle:
  - Тест простого случая (без обратной связи)
  - Тест с одним раундом уточнений
  - Тест с множественными раундами обратной связи
  - Тест генерации frontmatter update структуры
  - Тест обработки clarification requests/responses

**Когда использовать:**
- Критичные пользовательские сценарии
- WebSocket flow
- Комплексные операции
- Feedback cycle протокол

---

## Запуск тестов

### По типам

```bash
# Только unit-тесты (быстро, для разработки)
pytest -m unit

# Только integration-тесты (требуют сервисы)
pytest -m integration

# Только e2e-тесты
pytest -m e2e
```

### По скорости

```bash
# Исключить медленные тесты
pytest -m "not slow"

# Только медленные тесты (LLM API calls)
pytest -m slow
```

### По файлам/тестам

```bash
# Конкретный файл
pytest tests/integration/test_neo4j.py

# Конкретный тест
pytest tests/integration/test_neo4j.py::test_neo4j_connection_with_driver

pytest tests/integration/test_openai_generic_config.py::test_llm_chat_completion

# Все integration-тесты Neo4j
pytest tests/integration/test_neo4j.py -v

# Все LLM-тесты
pytest tests/integration/test_openai_generic_config.py -v
```

### С дополнительными опциями

```bash
# Подробный вывод
pytest -v

# Показать print-выводы
pytest -s

# Остановиться на первой ошибке
pytest -x

# Запустить последние упавшие тесты
pytest --lf

# Покрытие кода
pytest --cov=app --cov-report=html
# Откройте htmlcov/index.html в браузере
```

### Параллельный запуск (опционально)

```bash
# Установите pytest-xdist
uv pip install pytest-xdist

# Запуск в 4 процессах
pytest -n 4
```

---

## Фикстуры

Доступные фикстуры определены в [`conftest.py`](./conftest.py).

### Database Fixtures

#### `neo4j_driver` (scope: session)
Предоставляет Neo4j driver для всей тестовой сессии.

```python
def test_custom_query(neo4j_driver):
    with neo4j_driver.session() as session:
        result = session.run("MATCH (n) RETURN count(n)")
```

#### `neo4j_session` (scope: function)
Предоставляет Neo4j session для одного теста.

```python
def test_with_session(neo4j_session):
    neo4j_session.run("CREATE (n:Test {name: 'value'})")
```

#### `clean_neo4j_db` (scope: function)
Очищает БД перед и после теста. ⚠️ **Используйте только с тестовой БД!**

```python
@pytest.mark.integration
async def test_with_clean_db(clean_neo4j_db, neo4j_session):
    # БД пустая, можно создавать тестовые данные
    neo4j_session.run("CREATE (n:TestNode)")
```

### LLM Fixtures

#### `graphiti_instance` (scope: function, async)
Предоставляет настроенный экземпляр Graphiti с OpenRouter.

```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_with_graphiti(graphiti_instance):
    # Используйте для реальной обработки
    await graphiti_instance.add_episode(...)
```

#### `mock_llm_response` (scope: function)
Генератор мок-ответов LLM для unit-тестов.

```python
@pytest.mark.unit
def test_parser(mock_llm_response):
    response = mock_llm_response(content="Test", model="gpt-4")
    # Используйте вместо реального LLM
```

### Test Data Fixtures

#### `sample_note_content` (scope: function)
Предоставляет образец текста заметки.

```python
def test_processor(sample_note_content):
    assert "John Doe" in sample_note_content
```

#### `sample_note_payload` (scope: function)
Предоставляет готовый объект NotePayload.

```python
@pytest.mark.asyncio
async def test_process_note(sample_note_payload):
    result = await process_and_store_note(sample_note_payload)
```

---

## Маркеры

Маркеры для категоризации тестов (определены в `pytest.ini`).

### Основные маркеры

```python
@pytest.mark.unit           # Unit-тесты (быстрые, изолированные)
@pytest.mark.integration    # Integration-тесты (требуют сервисы)
@pytest.mark.e2e           # End-to-end тесты (полный flow)
@pytest.mark.slow          # Медленные тесты (>5 сек)
```

### Использование

```python
@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.asyncio
async def test_expensive_llm_call():
    """Этот тест медленный и требует OpenRouter"""
    pass
```

### Фильтрация при запуске

```bash
# Только integration, но без slow
pytest -m "integration and not slow"

# Unit или integration
pytest -m "unit or integration"
```

---

## Лучшие практики

### ✅ DO

1. **Используйте правильный тип теста**
   - Бизнес-логика без IO → `unit/`
   - Работа с БД/API → `integration/`
   - Полный сценарий → `e2e/`

2. **Маркируйте тесты**
   ```python
   @pytest.mark.integration
   @pytest.mark.asyncio
   async def test_db_operation():
       pass
   ```

3. **Используйте фикстуры для переиспользования**
   ```python
   def test_with_fixture(sample_note_payload, neo4j_session):
       # Чище, чем создавать данные в каждом тесте
   ```

4. **Тестируйте edge cases**
   ```python
   async def test_process_empty_note():
       """Проверяем обработку пустой заметки"""
       note = NotePayload(file_path="empty.md", content="")
       result = await process_and_store_note(note)
       assert result is not None
   ```

5. **Пишите осмысленные имена**
   ```python
   # ✅ Хорошо
   def test_note_payload_validates_empty_file_path():
       pass

   # ❌ Плохо
   def test_1():
       pass
   ```

### ❌ DON'T

1. **Не смешивайте типы тестов**
   ```python
   # ❌ Плохо: unit-тест с реальной БД
   @pytest.mark.unit
   def test_with_real_db(neo4j_session):  # Неправильно!
       pass
   ```

2. **Не используйте продакшн БД для тестов**
   ```bash
   # ⚠️ Используйте отдельную тестовую БД
   NEO4J_URI=bolt://localhost:7687  # Тестовая БД
   ```

3. **Не забывайте async/await**
   ```python
   # ❌ Плохо
   @pytest.mark.asyncio
   def test_async_function():  # Забыли async!
       await some_function()  # Будет ошибка

   # ✅ Хорошо
   @pytest.mark.asyncio
   async def test_async_function():
       await some_function()
   ```

4. **Не делайте тесты зависимыми друг от друга**
   ```python
   # ❌ Плохо: test_2 зависит от test_1
   def test_1():
       global data
       data = create_data()

   def test_2():
       use(data)  # Упадёт если test_1 не запустили
   ```

5. **Не расходуйте API-кредиты без необходимости**
   ```python
   # Используйте @pytest.mark.slow для дорогих операций
   @pytest.mark.integration
   @pytest.mark.slow  # ✅ Можно пропустить при разработке
   async def test_expensive_llm_call():
       pass
   ```

---

## Конфигурация окружения

### Переменные окружения для тестов

Тесты используют те же настройки из `.env`:

```bash
# Neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=test_password

# LLM Provider (OpenAI-compatible API, например Cloud.ru)
CLOUDRU_API_KEY=your_api_key
CLOUDRU_BASE_URL=https://api.cloudru.tech/v1
CLOUDRU_MAIN_MODEL=anthropic/claude-3.5-sonnet
CLOUDRU_SMALL_MODEL=anthropic/claude-3-haiku
CLOUDRU_EMBEDDING_MODEL=openai/text-embedding-3-small
```

⚠️ **Важно:** Используйте **отдельную тестовую БД Neo4j**, не продакшн!

---

## Покрытие кода

### Запуск с покрытием

```bash
# HTML-отчёт
pytest --cov=app --cov-report=html

# Откройте htmlcov/index.html в браузере
```

### Терминальный отчёт

```bash
pytest --cov=app --cov-report=term-missing
```

### Цели покрытия

- **Unit-тесты:** 80%+ для `models/`, `utils/`
- **Integration-тесты:** 60%+ для `services/`, `crud/`
- **E2E-тесты:** Критичные пользовательские сценарии

---

## Continuous Integration (CI)

### Пример для GitHub Actions

```yaml
# .github/workflows/test.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      neo4j:
        image: neo4j:latest
        env:
          NEO4J_AUTH: neo4j/testpassword
        ports:
          - 7687:7687

    steps:
      - uses: actions/checkout@v3

      - name: Install uv
        run: pip install uv

      - name: Install dependencies
        run: |
          cd backend
          uv pip install -r requirements.txt
          uv pip install -r requirements-dev.txt

      - name: Run unit tests
        run: pytest -m unit

      - name: Run integration tests (Neo4j only, без LLM)
        env:
          NEO4J_URI: bolt://localhost:7687
          NEO4J_USER: neo4j
          NEO4J_PASSWORD: testpassword
        run: pytest tests/integration/test_neo4j.py -v
```

---

## Troubleshooting

### Проблема: "No module named 'app'"

**Решение:** Убедитесь, что запускаете pytest из директории `backend/`:

```bash
cd backend/
pytest
```

### Проблема: Тесты не находятся

**Решение:** Проверьте конфигурацию в `pytest.ini`:

```ini
[pytest]
testpaths = tests
python_files = test_*.py
```

### Проблема: Neo4j connection refused

**Решение:**
1. Убедитесь, что Neo4j запущен: `docker ps` или `neo4j status`
2. Проверьте `NEO4J_URI` в `.env`
3. Проверьте пароль: `NEO4J_PASSWORD`

### Проблема: LLM Provider API errors

**Решение:**
1. Проверьте API-ключ в `.env` (например, `CLOUDRU_API_KEY`)
2. Проверьте баланс у провайдера (Cloud.ru и т.д.)
3. Убедитесь в правильности `BASE_URL` для вашего провайдера
4. Запускайте без slow-тестов: `pytest -m "not slow"`

---

## Дополнительные ресурсы

- [Pytest документация](https://docs.pytest.org/)
- [Pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
- [Neo4j Python Driver](https://neo4j.com/docs/python-manual/current/)
- [FastAPI Testing](https://fastapi.tiangolo.com/tutorial/testing/)

---

## Поддержка

Если у вас возникли вопросы или проблемы с тестами:

1. Проверьте этот README
2. Посмотрите примеры в существующих тестах
3. Проверьте фикстуры в `conftest.py`
4. Создайте issue в репозитории
