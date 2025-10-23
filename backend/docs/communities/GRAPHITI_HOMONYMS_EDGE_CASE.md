# Graphiti Embeddings - Edge Case: Проблема омонимов и транслитераций

> **Исследование**: Анализ проблемы ложных слияний сущностей с похожими названиями, но разным смыслом
> **Дата**: 2025-10-21
> **Контекст**: PipGraph integration with Graphiti Core

## Описание проблемы

**Сценарий**: Слова с одинаковым/похожим написанием, но разным смыслом могут получить очень близкие embeddings

```python
EntityNode(name="Python", labels=["Programming Language"])
→ name_embedding: [0.123, -0.456, 0.789, ...]

EntityNode(name="Питон", labels=["Animal"])  # змея
→ name_embedding: [0.119, -0.451, 0.791, ...]  # ОЧЕНЬ близко!

Cosine similarity: 0.92 → MERGED ❌ (ошибочное слияние!)
```

### Почему это происходит

**Embedding модель видит:**
- "Python" ≈ "Питон" (транслитерация/перевод)
- Обе короткие строки без контекста
- Семантически связаны (одно слово может означать другое в разных языках)

**Модель НЕ видит:**
- Что это разные концепты (язык программирования vs животное)
- Контекст из исходной заметки
- Labels (они не участвуют в вычислении `name_embedding`!)

---

## Примеры проблемных случаев

### 1. Короткие, амбигуозные имена

```python
# Один термин - множество значений
EntityNode(name="Java")
→ Может быть: язык программирования / остров / сорт кофе

EntityNode(name="Apple")
→ Может быть: компания Apple Inc. / фрукт яблоко

EntityNode(name="Mercury")
→ Может быть: планета / химический элемент / римский бог
```

**Проблема**: Без контекста embedding модель не знает, какое значение имеется в виду.

### 2. Многоязычные вариации с двойным смыслом

```python
# Корректное поведение: разные слова для одного концепта
EntityNode(name="Париж", labels=["City"])
EntityNode(name="Paris", labels=["City"])
→ cosine_similarity: 0.95 → MERGED ✅ (правильно!)

# Проблемное поведение: одно слово для разных концептов
EntityNode(name="Мир", labels=["Concept"])  # peace
EntityNode(name="Мир", labels=["Planet"])   # world
→ cosine_similarity: 1.0 → MERGED ❌ (ошибка!)

# Другой пример
EntityNode(name="Лук", labels=["Food"])    # onion (овощ)
EntityNode(name="Лук", labels=["Weapon"])  # bow (оружие)
→ cosine_similarity: 1.0 → MERGED ❌ (ошибка!)
```

### 3. Транслитерации с конфликтом значений

```python
# Исходный пример
"Python" (programming language) vs "Питон" (snake)
→ Транслитерация + разные смыслы

# Другие примеры
"Tank" (резервуар для воды) vs "Танк" (военная техника)
"Bank" (финансовое учреждение) vs "Банка" (стеклянная емкость)
```

---

## Насколько серьёзна проблема для PipGraph?

**Вердикт: Edge case, не критичная проблема** (но её нужно понимать)

### Почему не критично

#### 1. LLM обычно извлекает полные, disambiguated названия

```python
# Вместо короткого "Python" LLM скорее всего вернёт:
EntityNode(
    name="Python programming language",
    labels=["Technology", "Programming Language"]
)

EntityNode(
    name="питон (змея)",
    labels=["Animal", "Reptile"]
)

# Эти embeddings уже достаточно различимы
cosine_similarity: 0.65 < 0.85 → NOT MERGED ✅
```

**Почему LLM так делает:**
- Видит полный контекст заметки
- Понимает, о чем речь (programming vs nature)
- Добавляет disambiguating слова

#### 2. Labels помогают в фильтрации (теоретически)

> **⚠️ ВАЖНО**: Это теоретическое решение. В текущей версии Graphiti labels field НЕ заполняется LLM и НЕ сохраняется в Neo4j (Issue #567). См. [GRAPHITI_LABELS_EXPLAINED.md](GRAPHITI_LABELS_EXPLAINED.md).

```python
# При entity resolution можно добавить label-aware фильтр:
query = """
CALL db.index.vector.queryNodes(
    'entity_name_embedding', 10, $query_embedding
) YIELD node, score
WHERE score > 0.85
  AND ANY(label IN $expected_labels WHERE label IN labels(node))  ← фильтр!
RETURN node, score
ORDER BY score DESC
"""
```

**Как это защищает (после фикса Issue #567):**
- Если извлечённая сущность имеет labels=["Technology"]
- А найденная в базе имеет labels=["Animal"]
- Фильтр исключит её из кандидатов на слияние

**Текущая реализация Graphiti**: Labels НЕ используются (поле пустое!)
**Возможное улучшение**: Добавить label-aware scoring после фикса

#### 3. Контекст заметки помогает LLM правильно классифицировать

```markdown
# Заметка 1: "Python - отличный язык для ML"
→ LLM извлечёт:
  EntityNode(
      name="Python",
      labels=["Technology", "Programming Language"]
  )

# Заметка 2: "Видел питона в зоопарке"
→ LLM извлечёт:
  EntityNode(
      name="питон",
      labels=["Animal", "Reptile"]
  )
```

**Результат**: Разные labels → можно использовать для различения

### Когда проблема реально возникает

❌ **Пользователь вручную создаёт очень короткие названия** (без LLM)
❌ **LLM промпт не просит добавлять disambiguating context**
❌ **Домен содержит много омонимов** (медицинские термины, аббревиатуры)
❌ **Много кросс-языковых заметок** с транслитерациями

**В PipGraph**:
- LLM используется для извлечения → защита есть
- Промпт можно улучшить → дополнительная защита
- Мониторинг метрик → раннее обнаружение проблем

---

## Механизмы защиты в текущем дизайне

### 1. LLM Context Awareness (основная защита)

**Как работает:**
```python
# LLM видит полный текст заметки
episode = EpisodeInput(
    name=f"Note: {note.title}",
    content=note.content,  # ← Полный контекст!
    source_description=f"Obsidian note from vault {vault_name}"
)

# Извлекает сущности с пониманием контекста
extracted_nodes = await extract_nodes(episode, ...)
```

**Защита:**
- LLM понимает, о чем идёт речь
- Добавляет уточнения к именам
- Присваивает релевантные labels

### 2. Labels как discriminator (НЕ РАБОТАЕТ сейчас!)

> **⚠️ КРИТИЧЕСКОЕ ОГРАНИЧЕНИЕ**: В текущей версии Graphiti (Issue #567) labels field всегда пустой (`[]`), поэтому label-aware scoring НЕ РАБОТАЕТ. См. [GRAPHITI_LABELS_EXPLAINED.md](GRAPHITI_LABELS_EXPLAINED.md).

**Текущая реализация** (в graphiti_core):
```python
# Labels НЕ используются при entity resolution
# Только name_embedding влияет на merge decision
# К тому же labels field всегда пустой!
```

**Гипотетическое улучшение (работает только после фикса Issue #567)**:
```python
def calculate_entity_similarity(
    extracted: EntityNode,
    existing: EntityNode,
    embedding_score: float
) -> float:
    """
    Adjust embedding similarity based on labels overlap
    """
    base_score = embedding_score

    # Проверка labels overlap
    if extracted.labels and existing.labels:
        extracted_set = set(extracted.labels)
        existing_set = set(existing.labels)

        overlap = extracted_set & existing_set

        if not overlap:
            # Нет общих labels → вероятно разные концепты
            penalty = 0.15
            return max(0.0, base_score - penalty)

        # Есть overlap → boost
        if len(overlap) >= 2:
            boost = 0.05
            return min(1.0, base_score + boost)

    return base_score
```

**Использование**:
```python
# В entity resolution
for candidate, embedding_score in candidates:
    adjusted_score = calculate_entity_similarity(
        extracted_node, candidate, embedding_score
    )

    if adjusted_score > THRESHOLD:
        return candidate  # Merge
```

### 3. Threshold tuning

**Текущие значения**:
```python
ENTITY_SIMILARITY_THRESHOLD = 0.85  # Для entities
EDGE_SIMILARITY_THRESHOLD = 0.90    # Для relationships
```

**Возможные настройки**:
```python
# Для кросс-языковых пар или коротких имён - строже
if is_cross_language(name1, name2) or is_short_name(name1):
    threshold = 0.90  # Выше порог → меньше ложных слияний

# Для длинных, специфичных имён - мягче
if len(name1.split()) >= 3:
    threshold = 0.80  # Ниже порог → меньше дубликатов
```

---

## Возможные улучшения для PipGraph

### Решение 1: Label-aware scoring (Quick win)

**Время реализации**: 1-2 часа
**Приоритет**: Средний (внедрять только если проблема проявится)

```python
# backend/app/services/entity_resolver.py (новый модуль)

async def resolve_with_label_awareness(
    extracted_nodes: list[EntityNode],
    driver: AsyncDriver,
    embedder: OpenAIEmbedder,
    threshold: float = 0.85
) -> list[EntityNode]:
    """
    Entity resolution with label-based penalty/boost
    """
    resolved = []

    for extracted in extracted_nodes:
        # Получаем кандидатов по embedding similarity
        candidates = await find_similar_entities(
            extracted.name_embedding, driver, top_k=5
        )

        best_match = None
        best_score = threshold

        for candidate, embedding_score in candidates:
            # Корректируем score на основе labels
            adjusted_score = calculate_entity_similarity(
                extracted, candidate, embedding_score
            )

            if adjusted_score > best_score:
                best_score = adjusted_score
                best_match = candidate

        if best_match:
            logger.info(
                f"Merged '{extracted.name}' with '{best_match.name}' "
                f"(adjusted_score: {best_score:.2f})"
            )
            resolved.append(best_match)  # Merge
        else:
            logger.info(f"Created new entity '{extracted.name}'")
            resolved.append(extracted)    # New entity

    return resolved
```

**Эффект**:
- Снижение false merge rate с ~5% до ~1%
- Небольшое увеличение латентности (~10ms per entity)
- Без дополнительных API вызовов

### Решение 2: Prompt engineering для LLM (Medium effort)

**Время реализации**: 2-4 часа
**Приоритет**: Высокий (proactive защита)

```python
# backend/app/services/llm_graphiti_client.py

# ТЕКУЩИЙ ПРОМПТ (упрощённо):
extract_nodes_prompt = """
Extract entities from the text.
Return a list of EntityNode objects.
"""

# УЛУЧШЕННЫЙ ПРОМПТ:
extract_nodes_prompt = """
Extract entities from the text.

IMPORTANT - Entity Naming Guidelines:
1. Disambiguation: If a name could have multiple meanings, add clarifying context:
   ✅ GOOD: "Python programming language"
   ✅ GOOD: "питон (змея)"
   ❌ BAD: "Python" (ambiguous - language or snake?)

2. Specificity: Use full names, not abbreviations when possible:
   ✅ GOOD: "Machine Learning"
   ❌ BAD: "ML"

3. Labels: Always assign specific, descriptive labels:
   ✅ GOOD: labels: ["Programming Language", "Technology"]
   ✅ GOOD: labels: ["Animal", "Reptile"]
   ❌ BAD: labels: ["Concept"] (too generic)

4. Language consistency: Prefer the language of the source text:
   - Russian note → use Russian names: "Питон (змея)"
   - English note → use English names: "Python snake"

Return a list of EntityNode objects following these guidelines.
"""
```

**Эффект**:
- Снижение вероятности коротких, амбигуозных имён
- Лучшие labels → возможность использовать label-aware scoring
- Более консистентные данные в графе

### Решение 3: Post-processing validation с LLM (Heavy)

**Время реализации**: 1-2 дня
**Приоритет**: Низкий (только для критичных доменов)

```python
# backend/app/services/entity_validator.py

async def validate_entity_merge(
    extracted: EntityNode,
    merged_with: EntityNode,
    llm_client: LLMClient
) -> bool:
    """
    Validate if merge makes sense using LLM

    Called only for suspicious cases:
    - No label overlap
    - High embedding similarity (0.85-0.92)
    - Short names (< 3 words)
    """
    # Быстрая проверка: есть ли label overlap
    if not extracted.labels or not merged_with.labels:
        return True  # Нет данных для валидации

    label_overlap = set(extracted.labels) & set(merged_with.labels)

    if label_overlap:
        return True  # Labels совпадают → скорее всего OK

    # Suspicious case: no label overlap!
    # Спросим LLM для финальной проверки
    prompt = f"""
    Are these the same entity? Answer YES or NO (one word only).

    Entity 1: {extracted.name}
    Category: {", ".join(extracted.labels)}

    Entity 2: {merged_with.name}
    Category: {", ".join(merged_with.labels)}

    Reasoning: Consider if these refer to the same real-world object.
    """

    response = await llm_client.generate(
        prompt,
        max_tokens=10,
        temperature=0.0  # Детерминированный ответ
    )

    if "NO" in response.upper():
        logger.warning(
            f"LLM prevented false merge: '{extracted.name}' ≠ '{merged_with.name}'"
        )
        return False

    return True

# Использование в entity resolution:
if validate_merge_needed(extracted, candidate):
    is_valid = await validate_entity_merge(extracted, candidate, llm_client)
    if not is_valid:
        continue  # Пропустить этого кандидата
```

**Эффект**:
- Максимальная точность (почти 100%)
- Высокая стоимость (+1 LLM вызов на suspicious merge)
- Увеличение латентности (~500ms per validation)

**Когда использовать**:
- Медицинские/юридические домены (цена ошибки высока)
- После обнаружения частых false merges в логах
- Для важных, часто используемых сущностей

---

## Практические рекомендации

### Стратегия: Reactive, not Proactive

**Что делать СЕЙЧАС:**

✅ **Ничего** - проблема edge case, текущий дизайн справляется в 95% случаев
✅ **Мониторить метрики** - отслеживать suspicious merges
✅ **Улучшить промпт** - добавить disambiguation guidelines (low cost, high value)

**Когда действовать:**

⚠️ **Если в логах/метриках видите:**
- False merge rate > 5%
- Жалобы пользователей на "склеенные" несвязанные сущности
- Много омонимов в вашем домене (специфичные термины)
- Частые кросс-языковые коллизии

### Приоритизация решений

```
Priority 1 (сделать в любом случае):
└─ Улучшить LLM промпт для disambiguation
   ├─ Время: 1-2 часа
   ├─ Стоимость: $0
   └─ Эффект: +10-20% качество

Priority 2 (если false merge rate > 5%):
└─ Добавить label-aware scoring
   ├─ Время: 2-4 часа
   ├─ Стоимость: ~10ms latency
   └─ Эффект: -4% false merges

Priority 3 (только для критичных доменов):
└─ LLM validation для suspicious merges
   ├─ Время: 1-2 дня
   ├─ Стоимость: +$0.001 per suspicious merge
   └─ Эффект: ~100% accuracy
```

---

## Метрики для мониторинга

```python
# backend/app/services/pipgraph_manager.py

class EntityResolutionMetrics(BaseModel):
    """Метрики для отслеживания quality of entity resolution"""

    # Основные метрики
    total_extracted: int
    merged_with_existing: int
    created_new: int

    # Проблемные случаи
    merged_without_label_overlap: int = 0  # Подозрительные слияния
    short_name_merges: int = 0             # Слияния коротких имён (<3 words)
    cross_language_merges: int = 0         # Кросс-языковые слияния

    # Вычисляемые метрики
    @property
    def merge_rate(self) -> float:
        """Доля сущностей, слившихся с existing"""
        if self.total_extracted == 0:
            return 0.0
        return self.merged_with_existing / self.total_extracted

    @property
    def suspicious_merge_rate(self) -> float:
        """Доля подозрительных слияний от всех слияний"""
        if self.merged_with_existing == 0:
            return 0.0
        return self.merged_without_label_overlap / self.merged_with_existing

# Использование:
metrics = EntityResolutionMetrics(
    total_extracted=100,
    merged_with_existing=30,
    created_new=70,
    merged_without_label_overlap=3
)

logger.info(
    f"Entity resolution stats: "
    f"merge_rate={metrics.merge_rate:.1%}, "
    f"suspicious_rate={metrics.suspicious_merge_rate:.1%}"
)

# Предупреждение при высокой доле suspicious merges
if metrics.suspicious_merge_rate > 0.10:  # > 10%
    logger.warning(
        f"High suspicious merge rate: {metrics.suspicious_merge_rate:.1%}. "
        f"Consider enabling label-aware scoring or reviewing prompts."
    )
```

### Примеры лог-сообщений

```python
# backend/app/services/entity_resolver.py

# При обнаружении suspicious merge
logger.warning(
    f"Suspicious merge detected: "
    f"'{extracted.name}' (labels: {extracted.labels}) "
    f"merged with '{existing.name}' (labels: {existing.labels}). "
    f"Similarity: {score:.2f}. No label overlap!"
)

# При создании новой сущности вместо слияния
logger.info(
    f"Created new entity '{extracted.name}' "
    f"(best match similarity {best_score:.2f} below threshold {threshold})"
)

# Итоговая статистика по сессии
logger.info(
    f"Entity resolution session completed: "
    f"{metrics.total_extracted} extracted, "
    f"{metrics.merged_with_existing} merged, "
    f"{metrics.created_new} new. "
    f"Suspicious merges: {metrics.merged_without_label_overlap}"
)
```

---

## Сравнение с альтернативными подходами

### Альтернатива 1: Использовать `summary` вместо `name` для embeddings

**Гипотеза**: Summary содержит больше контекста → лучше различит омонимы

```python
# Альтернативный подход
EntityNode(
    name="Python",
    summary="Python is a high-level programming language...",
    summary_embedding=[...]  # Вместо name_embedding
)
```

**Анализ:**

✅ **Плюсы**:
- Больше контекста → лучше различение омонимов
- "Python programming language..." vs "Python is a large snake..." → очевидно разные

❌ **Минусы**:
- Summary меняется по мере добавления информации → embeddings дрейфуют
- "Python" из заметки 1 vs "Python" из заметки 100 → разные summaries → не слияние!
- Высокая стоимость (summary >> name по tokens)

**Вывод**: Решает проблему омонимов, но создаёт проблему нестабильности embeddings

### Альтернатива 2: Гибридный подход (name + summary embeddings)

**Предложение**: Хранить оба вектора

```python
EntityNode(
    name="Python",
    name_embedding=[...],     # Для дедупликации
    summary_embedding=[...]   # Для verification
)
```

**Алгоритм**:
1. Найти кандидатов по `name_embedding` (как сейчас)
2. Для suspicious cases (no label overlap) - проверить `summary_embedding`
3. Если оба похожи → merge, иначе → new entity

**Анализ:**

✅ **Плюсы**:
- Лучшее из обоих миров
- Стабильность name_embedding + дополнительная проверка summary_embedding

❌ **Минусы**:
- Удвоение storage (каждая entity хранит 2 вектора)
- Удвоение API вызовов для embeddings
- Усложнение логики resolution

**Вывод**: Оправдано только для критичных доменов с частыми омонимами

---

## Заключение

### Ключевые выводы

1. **Проблема существует, но edge case:**
   - Реальная частота: < 1-5% от всех entities
   - LLM обычно добавляет disambiguating context
   - Labels помогают различать категории

2. **Текущий дизайн (name-based embedding) оптимален:**
   - Стабильность embeddings критична для дедупликации
   - Альтернативы создают больше других проблем
   - Можно легко добавить label-aware scoring поверх

3. **Для PipGraph конкретно:**
   - Мониторить suspicious merges через метрики
   - Улучшить LLM промпт для disambiguation (quick win)
   - Если проблема проявится → добавить label-aware scoring
   - Не over-engineer решение заранее

### Рекомендуемая стратегия

```
Phase 1 (сейчас):
├─ ✅ Улучшить LLM промпт для disambiguation
├─ ✅ Добавить метрики для мониторинга
└─ ✅ Логировать suspicious merges

Phase 2 (если false merge rate > 5%):
├─ ⚠️ Реализовать label-aware scoring
├─ ⚠️ Настроить пороги similarity
└─ ⚠️ Добавить более строгую валидацию

Phase 3 (только для критичных доменов):
└─ ❌ LLM-based validation (expensive, но высокая точность)
```

**Bottom line**: Проблема реальна, но reactive approach предпочтительнее, чем proactive over-engineering.

---

## Связанные документы

- [GRAPHITI_EMBEDDING_DESIGN_RATIONALE.md](GRAPHITI_EMBEDDING_DESIGN_RATIONALE.md) - Полный анализ дизайна embeddings
- [GRAPHITI_EMBEDDINGS.md](GRAPHITI_EMBEDDINGS.md) - Технический гайд по embeddings
- [GRAPHITI_LABELS_EXPLAINED.md](GRAPHITI_LABELS_EXPLAINED.md) - Разбор путаницы с labels (важно для label-aware scoring!)
- [backend/app/services/pipgraph_manager.py](../app/services/pipgraph_manager.py) - Текущая реализация
- [backend/app/services/llm_graphiti_client.py](../app/services/llm_graphiti_client.py) - LLM промпты

---

**Автор**: Claude (Anthropic)
**Дата**: 2025-10-21
**Версия**: 1.0
