# Работа с корутинами в FastAPI

## Проблема: "coroutine was never awaited"

### Описание ошибки

При работе с асинхронными функциями в FastAPI можно получить warning:

```
RuntimeWarning: coroutine 'function_name' was never awaited
  await dependant.call(**solved_result.values)
RuntimeWarning: Enable tracemalloc to get the object allocation traceback
```

Это происходит, когда асинхронная функция вызывается без `await`.

## Пример из реального кода

### ❌ Неправильно (до исправления)

```python
@router.websocket("/ws/notes/process")
async def process_note_websocket(websocket: WebSocket):
    """
    Принимает WebSocket соединение для полного цикла обработки заметки.
    """
    await websocket.accept()
    try:
        data = await websocket.receive_json()
        payload = NotePayload(**data)

        # Отправляем клиенту подтверждение о начале работы
        await websocket.send_json({
            "status": "processing",
            "message": f"Note '{payload.file_path}' received, starting processing..."
        })

        # ❌ ОШИБКА: вызов async функции без await
        graph_data = note_processor.process_and_store_note(payload)

        # Отправляем финальный результат
        await websocket.send_json({
            "status": "done",
            "data": graph_data.dict()  # Это упадёт, т.к. graph_data - корутина!
        })

    except WebSocketDisconnect:
        print("Client disconnected")
    finally:
        await websocket.close()
```

### ✅ Правильно (после исправления)

```python
@router.websocket("/ws/notes/process")
async def process_note_websocket(websocket: WebSocket):
    """
    Принимает WebSocket соединение для полного цикла обработки заметки.
    """
    await websocket.accept()
    try:
        data = await websocket.receive_json()
        payload = NotePayload(**data)

        # Отправляем клиенту подтверждение о начале работы
        await websocket.send_json({
            "status": "processing",
            "message": f"Note '{payload.file_path}' received, starting processing..."
        })

        # ✅ ПРАВИЛЬНО: используем await для async функции
        graph_data = await note_processor.process_and_store_note(payload)

        # Отправляем финальный результат
        await websocket.send_json({
            "status": "done",
            "data": graph_data.dict()  # Теперь graph_data - это реальный объект
        })

    except WebSocketDisconnect:
        print("Client disconnected")
    finally:
        await websocket.close()
```

## Что происходит внутри

### Без `await`:

```python
# Создаётся объект корутины, но код не выполняется
graph_data = note_processor.process_and_store_note(payload)
# graph_data = <coroutine object process_and_store_note at 0x...>
```

- Функция `process_and_store_note` **не вызывается**
- Переменная содержит объект корутины, а не результат
- При попытке вызвать `.dict()` получаем AttributeError
- FastAPI выдаёт RuntimeWarning

### С `await`:

```python
# Корутина выполняется и ждём результат
graph_data = await note_processor.process_and_store_note(payload)
# graph_data = GraphData(entities=[...], relationships=[...])
```

- Функция **выполняется** и возвращает результат
- Переменная содержит реальный объект `GraphData`
- Метод `.dict()` работает корректно
- Никаких warnings

## Правила работы с async/await

### 1. Async функции всегда возвращают корутины

```python
async def fetch_data():
    return {"result": 42}

# ❌ Неправильно
data = fetch_data()  # data - это корутина, не dict!

# ✅ Правильно
data = await fetch_data()  # data = {"result": 42}
```

### 2. `await` можно использовать только внутри `async def`

```python
# ❌ Неправильно - SyntaxError
def sync_function():
    data = await async_function()  # Ошибка!

# ✅ Правильно
async def async_function():
    data = await another_async_function()
```

### 3. FastAPI эндпоинты должны быть async

```python
# ✅ Правильно - для WebSocket и длительных операций
@router.websocket("/ws/process")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    result = await long_running_task()
    await websocket.send_json(result)

# ✅ Тоже правильно - для быстрых sync операций
@router.get("/quick")
def quick_endpoint():
    return {"status": "ok"}

# ⚠️ Смешанный подход - async endpoint, но sync функция
@router.get("/mixed")
async def mixed_endpoint():
    result = sync_function()  # Нет await - это OK, если функция sync
    return result
```

### 4. Определение типа функции

```python
# Async функция - нужен await
async def process_data(data: str) -> dict:
    return {"processed": data}

# Sync функция - await не нужен
def validate_data(data: str) -> bool:
    return len(data) > 0

# Использование
async def handler():
    # ✅ await для async
    result = await process_data("test")

    # ✅ без await для sync
    is_valid = validate_data("test")
```

## Отладка проблем с корутинами

### Как обнаружить проблему:

1. **RuntimeWarning в логах**:
   ```
   RuntimeWarning: coroutine 'function_name' was never awaited
   ```

2. **AttributeError при попытке использовать результат**:
   ```python
   AttributeError: 'coroutine' object has no attribute 'dict'
   ```

3. **Проверка типа**:
   ```python
   import inspect

   result = some_function()
   if inspect.iscoroutine(result):
       print("Это корутина! Нужен await")
   ```

### Как исправить:

1. Найти вызов async функции
2. Добавить `await` перед вызовом
3. Убедиться, что вызывающая функция тоже `async`

## Best Practices

### ✅ DO:

- Используйте `await` для всех async функций
- Делайте WebSocket эндпоинты асинхронными
- Используйте async для I/O операций (БД, API, файлы)

### ❌ DON'T:

- Не забывайте `await` при вызове async функций
- Не делайте CPU-intensive операции в async функциях
- Не смешивайте sync/async без понимания последствий

## Дополнительные ресурсы

- [FastAPI Async SQL Databases](https://fastapi.tiangolo.com/advanced/async-sql-databases/)
- [Python asyncio documentation](https://docs.python.org/3/library/asyncio.html)
- [Real Python: Async IO in Python](https://realpython.com/async-io-python/)
