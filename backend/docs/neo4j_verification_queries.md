# Neo4j Verification Queries

**Дата создания:** 2025-11-21
**Версия:** 1.0
**Статус:** Active
**Цель:** Готовые Cypher запросы для проверки корректности работы PARA workflow

---

## Обзор

Этот документ содержит готовые Cypher запросы для проверки:
- Корректности схемы данных
- Работы CRUD операций
- Состояния :SUGGESTS и :IS_PART_OF связей
- Результатов извлечения сущностей
- Чистоты графа

---

## 1. Schema Verification

### 1.1 Проверка Constraints

```cypher
SHOW CONSTRAINTS;
```

Ожидаемые constraints:
- `Episodic.name` (UNIQUE)
- `Project.id` (UNIQUE)
- `Area.id` (UNIQUE)
- `Resource.id` (UNIQUE)

### 1.2 Проверка Indexes

```cypher
SHOW INDEXES;
```

Ожидаемые indexes:
- `Entity.uuid`
- `SUGGESTS.suggestion_id` (relationship property index)

---

## 2. No-Cache Policy Verification

### 2.1 Episodic без project_id

```cypher
// Episodic должен быть БЕЗ поля project_id
MATCH (e:Episodic {name: "Notes/test.md"})
RETURN properties(e);
// Ожидаем: name, content, created_at, valid_at, uuid, source
// НЕ должно быть: project_id
```

### 2.2 Все Episodic без project_id

```cypher
// Проверить что ни у одного Episodic нет project_id
MATCH (e:Episodic)
WHERE e.project_id IS NOT NULL
RETURN e.name, e.project_id;
// Должен быть пустой результат
```

---

## 3. SUGGESTS Relationship Verification

### 3.1 Множественные :SUGGESTS между узлами

```cypher
// Проверить что между Episodic и Project может быть несколько :SUGGESTS
MATCH (e:Episodic {name: "Notes/test.md"})-[r:SUGGESTS]->(p:Project)
RETURN
    r.suggestion_id,
    r.suggestion_type,
    r.confidence,
    r.target_field,
    r.suggested_value
ORDER BY r.suggestion_type;
// Ожидаем 2 ребра:
// 1. suggestion_type="link"
// 2. suggestion_type="property_update", target_field="name"
```

### 3.2 Все атрибуты :SUGGESTS

```cypher
// Проверить все атрибуты связи :SUGGESTS
MATCH ()-[r:SUGGESTS]->()
RETURN
    r.suggestion_id,
    r.suggestion_type,
    r.confidence,
    r.reasoning,
    r.target_field,
    r.suggested_value,
    r.created_at
LIMIT 5;
```

### 3.3 Количество :SUGGESTS по типу

```cypher
// Статистика по типам предложений
MATCH ()-[r:SUGGESTS]->()
RETURN r.suggestion_type, count(*) as count
ORDER BY count DESC;
```

---

## 4. IS_PART_OF Relationship Verification

### 4.1 Episodic с подтвержденным контекстом

```cypher
// Проверить :IS_PART_OF связь
MATCH (e:Episodic {name: "Notes/test.md"})-[r:IS_PART_OF]->(p)
RETURN e.name, type(r), p.name, p.id, labels(p);
```

### 4.2 Все Episodic и их контексты

```cypher
// Список всех Episodic с их контейнерами
MATCH (e:Episodic)-[r:IS_PART_OF]->(p)
RETURN e.name, p.name as container, labels(p)[0] as type
ORDER BY e.name;
```

---

## 5. Transformation Verification

### 5.1 После confirm link

```cypher
// :SUGGESTS с type="link" должно исчезнуть
MATCH (e:Episodic {name: "Notes/test.md"})-[r:SUGGESTS {suggestion_type: "link"}]->(p:Project)
RETURN count(r) as link_suggestions;
// Ожидаем: 0

// :IS_PART_OF должно появиться
MATCH (e:Episodic {name: "Notes/test.md"})-[r:IS_PART_OF]->(p:Project)
RETURN p.name;
// Ожидаем: "Mock Project Alpha"
```

### 5.2 После confirm property_update

```cypher
// Проверить обновление свойства Project
MATCH (p:Project {id: "mock-project-alpha"})
RETURN p.name;
// Ожидаем: "Mock Project Alpha v2" (или новое значение)

// :SUGGESTS с type="property_update" должно исчезнуть
MATCH (e:Episodic)-[r:SUGGESTS {suggestion_type: "property_update"}]->(p:Project)
RETURN count(r) as update_suggestions;
// Ожидаем: 0
```

---

## 6. Entity & MENTIONS Verification

### 6.1 Проверка Entity узлов

```cypher
// Все Entity узлы
MATCH (e:Entity)
RETURN e.uuid, e.name, labels(e) as all_labels
LIMIT 10;
```

### 6.2 Проверка :MENTIONS связей

```cypher
// Entities связанные с Episodic
MATCH (ep:Episodic {name: "Notes/test.md"})-[r:MENTIONS]->(e:Entity)
RETURN ep.name, e.name, e.summary, r.status;
// Ожидаем: 2-3 Entity с status="confirmed"
```

### 6.3 Проверка контекста в Entity

```cypher
// Entity summaries должны содержать имя контейнера
MATCH (ep:Episodic)-[r:MENTIONS]->(e:Entity)
WHERE ep.name STARTS WITH "Notes/test"
RETURN e.name, e.summary;
// Summary должен содержать имя проекта из контекста
```

### 6.4 Количество Entity по Episodic

```cypher
// Статистика Entity на Episodic
MATCH (ep:Episodic)-[r:MENTIONS]->(e:Entity)
RETURN ep.name, count(e) as entity_count
ORDER BY entity_count DESC;
```

---

## 7. Graph Cleanliness Verification

### 7.1 Orphan Episodics (без контекста)

```cypher
// Episodic без :IS_PART_OF (должны быть только в процессе обработки)
MATCH (e:Episodic)
WHERE NOT EXISTS((e)-[:IS_PART_OF]->())
RETURN e.name, e.created_at;
// Должен быть пустой результат после завершения workflow
```

### 7.2 Незавершенные :SUGGESTS

```cypher
// Все активные suggestions (требуют решения)
MATCH (e:Episodic)-[r:SUGGESTS]->(p)
RETURN e.name, r.suggestion_id, r.suggestion_type, r.confidence
ORDER BY e.name;
// После завершения workflow должен быть пустой
```

### 7.3 Полная статистика графа

```cypher
// Общая статистика
MATCH (n)
RETURN labels(n)[0] as type, count(*) as count
ORDER BY count DESC;
```

### 7.4 Статистика связей

```cypher
// Статистика по типам связей
MATCH ()-[r]->()
RETURN type(r) as relationship, count(*) as count
ORDER BY count DESC;
```

---

## 8. Workflow State Verification

### 8.1 Полное состояние для конкретной заметки

```cypher
// Полное состояние обработки заметки
MATCH (e:Episodic {name: "Notes/test_iteration5_workflow.md"})
OPTIONAL MATCH (e)-[ip:IS_PART_OF]->(container)
OPTIONAL MATCH (e)-[s:SUGGESTS]->(suggested)
OPTIONAL MATCH (e)-[m:MENTIONS]->(entity:Entity)
RETURN
    e.name as episodic,
    container.name as context,
    labels(container)[0] as context_type,
    count(DISTINCT s) as pending_suggestions,
    count(DISTINCT entity) as extracted_entities;
```

### 8.2 Детали suggestions для заметки

```cypher
// Детали всех suggestions для заметки
MATCH (e:Episodic {name: "Notes/test.md"})-[r:SUGGESTS]->(p)
RETURN
    r.suggestion_id,
    r.suggestion_type,
    r.confidence,
    r.reasoning,
    p.name as target_container,
    r.target_field,
    r.suggested_value;
```

---

## 9. Debug Queries

### 9.1 Найти Episodic по пути

```cypher
// Поиск Episodic
MATCH (e:Episodic)
WHERE e.name CONTAINS "test"
RETURN e.name, e.created_at
ORDER BY e.created_at DESC;
```

### 9.2 Найти Project по ID или имени

```cypher
// Поиск Project
MATCH (p:Project)
WHERE p.id CONTAINS "mock" OR p.name CONTAINS "Mock"
RETURN p.id, p.name, p.status;
```

### 9.3 История изменений Project

```cypher
// Проверить текущее состояние Project
MATCH (p:Project {id: "mock-project-alpha"})
RETURN properties(p);
```

### 9.4 Все связи для Episodic

```cypher
// Все связи от Episodic
MATCH (e:Episodic {name: "Notes/test.md"})-[r]->(n)
RETURN type(r) as relationship, labels(n)[0] as target_type, n.name
ORDER BY type(r);
```

---

## 10. Cleanup Queries

### 10.1 Удаление тестовых данных

```cypher
// Удалить все тестовые Episodic и их связи
MATCH (e:Episodic)
WHERE e.name STARTS WITH "Notes/test"
DETACH DELETE e;
```

### 10.2 Удаление тестовых Project

```cypher
// Удалить тестовые проекты
MATCH (p:Project)
WHERE p.id STARTS WITH "test-" OR p.id STARTS WITH "mock-"
DETACH DELETE p;
```

### 10.3 Удаление mock Entity

```cypher
// Удалить mock entities
MATCH (e:Entity)
WHERE e.uuid STARTS WITH "mock-entity-"
DETACH DELETE e;
```

### 10.4 Полная очистка тестовых данных

```cypher
// Комплексная очистка
MATCH (n)
WHERE (n:Episodic AND n.name STARTS WITH "Notes/test")
   OR (n:Project AND (n.id STARTS WITH "test-" OR n.id STARTS WITH "mock-"))
   OR (n:Entity AND n.uuid STARTS WITH "mock-entity-")
DETACH DELETE n;
```

---

## Quick Reference

### После запуска workflow

```cypher
// Проверить что suggestions созданы
MATCH (e:Episodic {name: $note_path})-[r:SUGGESTS]->(p)
RETURN r.suggestion_id, r.suggestion_type, r.confidence;
```

### После confirm link

```cypher
// Проверить что :IS_PART_OF создан
MATCH (e:Episodic {name: $note_path})-[:IS_PART_OF]->(p)
RETURN p.name;
```

### После завершения workflow

```cypher
// Проверить финальное состояние
MATCH (e:Episodic {name: $note_path})
OPTIONAL MATCH (e)-[:IS_PART_OF]->(p)
OPTIONAL MATCH (e)-[:MENTIONS]->(ent)
WITH e, p, count(ent) as entities
WHERE NOT EXISTS((e)-[:SUGGESTS]->())
RETURN e.name, p.name as context, entities;
```

---

## Usage

1. Откройте Neo4j Browser: `http://localhost:7474`
2. Замените `"Notes/test.md"` на актуальный путь к заметке
3. Выполните запросы после каждого этапа workflow
4. Сравните результаты с ожидаемыми значениями

---

**Готово к использованию!** 🚀
