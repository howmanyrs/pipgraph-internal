
Нужно составить пошаговый план реализации задачи описанной в папке resolveflow

План должен состоять из отдльелныйх файлов, каждый из которых это отдельный этап с небольшим количеством шагов. 

План должен включать принятые подходы к реализации, чтобы не путаться:

Описываю принятые концепции и замечания:


@backend/docs/attend/resolveflow/01_PROBLEM_STATEMENT.md

Вопросы из раздела ## Вопросы для Обсуждения

```
1. **Уровень уверенности классификации**: При каком threshold не классифицировать заметку?
   - Предложение: Если confidence < 0.6, оставить `labels=[]`

2. **Смешанные заметки**: Что делать, если заметка - одновременно Project И Resource?
   - Предложение: Выбирать доминирующий тип, добавлять вторичный в metadata

3. **Реклассификация**: Можно ли изменить PARA-тип существующей заметки?
   - Предложение: Да, через отдельный API endpoint

4. **Fallback стратегия**: Что если classify_note_as_para() падает?
   - Предложение: Логировать ошибку, продолжать без PARA label
```

Эти вопросы будут решаться пользователем - точки интервенции. При определенном уровне confidence. Это часть архитектуры PipGraph, которую предстоить разработать на следующем этапе.


@backend/docs/attend/resolveflow/02_ARCHITECTURE_DECISION.md

Для решения PARA-Контекст для extract_edges
выбираем сразу вариант: Скопировать `extract_edges` из graphiti в локальный модуль.
(не делаем hack и wrapper)

Пропускаем описание тестирования и альтернативные архитектуры - делаем чистый план.

@backend/docs/attend/resolveflow/03_CLASSIFICATION_FLOW.md

Учитывя, что мы можем переспросить у пользователя - к какому типу относится заметка (Проект, заметка, и т.д.) и тут главное тонко подметить детали - возможно, наоборот, стоит использовать основную LLM, а не дешевую.

Описание метрик, кеширование и тестирования лучше делать отдельным этапом потом. Сейчас фокус на чистой реализации.


@backend/docs/attend/resolveflow/04_EDGE_ENRICHMENT.md

Реализуем необходимые модели и методы. Не используем hack,  а делаем Скопировать `extract_edges` из graphiti в локальный модуль.
Тесты пропускаем.


@backend/docs/attend/resolveflow/05_IMPLEMENTATION_PLAN.md

Работаем только над:
Phase 1: Core Classification (3-5 days)
  ├── Task 1.1: Create classify_note_as_para() method
  ├── Task 1.2: Modify EpisodicNode creation
  └── Task 1.3: Unit tests for classification

Phase 2: Edge Enrichment (2-3 days)
  ├── Task 2.1: Create extended edge types
  ├── Task 2.2: Build PARA edge prompts module
  └── Task 2.3: Integrate into extract_edges

И необходимая документация по созданным решениям.


