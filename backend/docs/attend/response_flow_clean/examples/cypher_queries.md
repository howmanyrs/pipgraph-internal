// ============================================================================
// Канонические Cypher-запросы для MVP системы многоуровневых подтверждений
// ============================================================================
//
// Этот файл содержит готовые к использованию запросы для:
// - Создания схемы (индексы, constraints)
// - CRUD операций с UserCheckStatus
// - CRUD операций с PARA контейнерами
// - Dashboard-запросов
// - Аналитики
//
// Дата: 2025-11-17
// Версия: 1.0
//
// ============================================================================

// ============================================================================
// 1. СОЗДАНИЕ СХЕМЫ
// ============================================================================

// === Constraints (уникальность) ===

CREATE CONSTRAINT entity_uuid_unique IF NOT EXISTS
FOR (e:EntityNode) REQUIRE e.uuid IS UNIQUE;

CREATE CONSTRAINT check_id_unique IF NOT EXISTS
FOR (c:UserCheckStatus) REQUIRE c.id IS UNIQUE;

CREATE CONSTRAINT project_id_unique IF NOT EXISTS
FOR (p:Project) REQUIRE p.id IS UNIQUE;

CREATE CONSTRAINT area_id_unique IF NOT EXISTS
FOR (a:Area) REQUIRE a.id IS UNIQUE;

CREATE CONSTRAINT resource_id_unique IF NOT EXISTS
FOR (r:Resource) REQUIRE r.id IS UNIQUE;

CREATE CONSTRAINT note_path_unique IF NOT EXISTS
FOR (n:Note) REQUIRE n.path IS UNIQUE;

// === Constraints (обязательные поля) ===

CREATE CONSTRAINT check_status_exists IF NOT EXISTS
FOR (c:UserCheckStatus) REQUIRE c.status IS NOT NULL;

CREATE CONSTRAINT check_timestamp_exists IF NOT EXISTS
FOR (c:UserCheckStatus) REQUIRE c.timestamp IS NOT NULL;

CREATE CONSTRAINT project_name_exists IF NOT EXISTS
FOR (p:Project) REQUIRE p.name IS NOT NULL;

// === Индексы (производительность) ===

CREATE INDEX check_status IF NOT EXISTS
FOR (c:UserCheckStatus) ON (c.status);

CREATE INDEX check_timestamp IF NOT EXISTS
FOR (c:UserCheckStatus) ON (c.timestamp);

CREATE INDEX check_status_timestamp IF NOT EXISTS
FOR (c:UserCheckStatus) ON (c.status, c.timestamp);

CREATE INDEX entity_uuid IF NOT EXISTS
FOR (e:EntityNode) ON (e.uuid);

CREATE INDEX project_id IF NOT EXISTS
FOR (p:Project) ON (p.id);

CREATE INDEX area_id IF NOT EXISTS
FOR (a:Area) ON (a.id);

CREATE INDEX resource_id IF NOT EXISTS
FOR (r:Resource) ON (r.id);

CREATE INDEX note_path IF NOT EXISTS
FOR (n:Note) ON (n.path);


// ============================================================================
// 2. CRUD: UserCheckStatus
// ============================================================================

// === Создать новый UserCheckStatus и связать с entity ===

CREATE (check:UserCheckStatus {
    id: $check_id,
    status: $status,
    confirmation_level: $confirmation_level,
    confidence: $confidence,
    timestamp: datetime(),
    user_action: $user_action,
    modified_fields: $modified_fields,
    modifications: $modifications,
    user_comment: $user_comment,
    system_suggestion: $system_suggestion,
    auto_confirmed: $auto_confirmed,
    skip_count: $skip_count
})
WITH check
MATCH (entity:EntityNode {uuid: $entity_uuid})
CREATE (entity)-[:HAS_CHECK {is_current: true}]->(check)
RETURN check;

// === Получить текущий статус сущности ===

MATCH (e:EntityNode {uuid: $entity_uuid})-[:HAS_CHECK {is_current: true}]->(c:UserCheckStatus)
RETURN c;

// === Получить полную историю проверок ===

MATCH (e:EntityNode {uuid: $entity_uuid})-[:HAS_CHECK]->(current:UserCheckStatus)-[:NEXT*0..]->(history:UserCheckStatus)
RETURN current, history
ORDER BY current.timestamp DESC;

// === Обновить статус (транзакция) ===

// Шаг 1: Найти текущий check и сбросить is_current
MATCH (entity:EntityNode {uuid: $entity_uuid})-[r:HAS_CHECK {is_current: true}]->(old_check:UserCheckStatus)
SET r.is_current = false

// Шаг 2: Создать новый check
WITH entity, old_check
CREATE (new_check:UserCheckStatus {
    id: $new_check_id,
    status: $new_status,
    confirmation_level: $confirmation_level,
    timestamp: datetime(),
    user_action: $user_action,
    modified_fields: $modified_fields,
    modifications: $modifications,
    user_comment: $user_comment
})

// Шаг 3: Связать с entity
CREATE (entity)-[:HAS_CHECK {is_current: true}]->(new_check)

// Шаг 4: Связать с историей
CREATE (new_check)-[:NEXT]->(old_check)

RETURN new_check;


// ============================================================================
// 3. CRUD: PARA Containers
// ============================================================================

// === Создать Project ===

CREATE (p:Project {
    id: $project_id,
    name: $name,
    status: $status,
    deadline: date($deadline),
    goal: $goal,
    created_at: datetime(),
    team: $team,
    budget: $budget
})
RETURN p;

// === Создать Area ===

CREATE (a:Area {
    id: $area_id,
    name: $name,
    goal: $goal,
    review_frequency: $review_frequency,
    created_at: datetime(),
    active: true
})
RETURN a;

// === Создать Resource ===

CREATE (r:Resource {
    id: $resource_id,
    topic: $topic,
    category: $category,
    created_at: datetime(),
    tags: $tags
})
RETURN r;

// === Найти все активные проекты ===

MATCH (p:Project {status: "active"})
RETURN p
ORDER BY p.deadline ASC;

// === Найти проект по ID ===

MATCH (p:Project {id: $project_id})
RETURN p;

// === Связать заметку с проектом ===

MATCH (n:Note {path: $note_path})
MATCH (p:Project {id: $project_id})
CREATE (n)-[:IS_PART_OF {
    assigned_at: datetime(),
    user_confirmed: true
}]->(p)
RETURN n, p;

// === Найти все заметки проекта ===

MATCH (n:Note)-[:IS_PART_OF]->(p:Project {id: $project_id})
RETURN n
ORDER BY n.updated_at DESC;


// ============================================================================
// 4. DASHBOARD QUERIES (UI)
// ============================================================================

// === Pending Items: Что нужно подтвердить? ===

MATCH (e:EntityNode)-[:HAS_CHECK {is_current: true}]->(c:UserCheckStatus {status: 'pending'})
RETURN e.uuid, e.name, labels(e)[0] AS entity_type, c.confidence, c.timestamp
ORDER BY c.confidence ASC, c.timestamp ASC
LIMIT 20;

// === Pending по уровням (L1, L2, L3) ===

MATCH (e)-[:HAS_CHECK {is_current: true}]->(c:UserCheckStatus {status: 'pending'})
RETURN c.confirmation_level, count(*) AS count
ORDER BY count DESC;

// === Недавно подтвержденные сущности ===

MATCH (e:EntityNode)-[:HAS_CHECK {is_current: true}]->(c:UserCheckStatus)
WHERE c.status IN ['confirmed', 'modified']
AND c.timestamp >= datetime() - duration({days: 7})
RETURN e.name, labels(e)[0] AS entity_type, c.status, c.timestamp
ORDER BY c.timestamp DESC
LIMIT 50;

// === Заметки без PARA классификации ===

MATCH (n:Note)
WHERE NOT (n)-[:IS_PART_OF]->()
RETURN n.path, n.created_at
ORDER BY n.created_at DESC;

// === Orphan entities (без связей) ===

MATCH (e:EntityNode)
WHERE NOT (e)-[:HAS_CHECK]->()
RETURN e.uuid, e.name, labels(e)[0] AS entity_type;


// ============================================================================
// 5. ANALYTICS QUERIES
// ============================================================================

// === Статистика по статусам (за последнюю неделю) ===

MATCH (c:UserCheckStatus)
WHERE c.timestamp >= datetime() - duration({days: 7})
RETURN c.status, count(*) AS count
ORDER BY count DESC;

// === Статистика по типам сущностей и статусам ===

MATCH (e)-[:HAS_CHECK {is_current: true}]->(c:UserCheckStatus)
RETURN labels(e)[0] AS entity_type, c.status, count(*) AS count
ORDER BY entity_type, count DESC;

// === Самые часто модифицируемые поля ===

MATCH (c:UserCheckStatus {status: 'modified'})
UNWIND c.modified_fields AS field
RETURN field, count(*) AS modification_count
ORDER BY modification_count DESC
LIMIT 10;

// === Средняя уверенность по типам сущностей ===

MATCH (e)-[:HAS_CHECK {is_current: true}]->(c:UserCheckStatus)
WHERE c.confidence IS NOT NULL
RETURN labels(e)[0] AS entity_type,
       avg(c.confidence) AS avg_confidence,
       count(*) AS entity_count
ORDER BY avg_confidence DESC;

// === Топ проектов по количеству заметок ===

MATCH (n:Note)-[:IS_PART_OF]->(p:Project)
RETURN p.name, count(n) AS note_count, p.deadline, p.status
ORDER BY note_count DESC
LIMIT 10;

// === Пользовательская активность (подтверждения за день) ===

MATCH (c:UserCheckStatus)
WHERE c.user_action IS NOT NULL
AND c.timestamp >= datetime() - duration({days: 1})
RETURN date(c.timestamp) AS day,
       c.user_action,
       count(*) AS action_count
ORDER BY day DESC, action_count DESC;


// ============================================================================
// 6. AUDIT TRAIL (История изменений)
// ============================================================================

// === Полная история изменений для сущности ===

MATCH (e:EntityNode {uuid: $entity_uuid})-[:HAS_CHECK]->(c:UserCheckStatus)-[:NEXT*0..]->(h:UserCheckStatus)
RETURN e.name,
       c.status AS current_status,
       c.timestamp AS current_timestamp,
       collect({
           status: h.status,
           timestamp: h.timestamp,
           user_action: h.user_action,
           user_comment: h.user_comment
       }) AS history
ORDER BY c.timestamp DESC;

// === Кто и когда модифицировал сущность ===

MATCH (e:EntityNode {uuid: $entity_uuid})-[:HAS_CHECK]->(c:UserCheckStatus)
WHERE c.status = 'modified'
RETURN c.timestamp,
       c.modified_fields,
       c.modifications,
       c.user_comment
ORDER BY c.timestamp DESC;

// === Изменения в проекте за период ===

MATCH (n:Note)-[:IS_PART_OF]->(p:Project {id: $project_id})
MATCH (e:EntityNode)-[:HAS_CHECK]->(c:UserCheckStatus)
WHERE (n)-[:CONTAINS]->(e)
AND c.timestamp >= datetime($start_date)
AND c.timestamp <= datetime($end_date)
RETURN n.path,
       e.name,
       labels(e)[0] AS entity_type,
       c.status,
       c.timestamp
ORDER BY c.timestamp DESC;


// ============================================================================
// 7. ADVANCED QUERIES (для пост-MVP)
// ============================================================================

// === Найти похожие проекты (по названию) ===

MATCH (p:Project)
WHERE p.name CONTAINS $search_term
AND p.status = "active"
RETURN p.id, p.name, p.deadline
ORDER BY p.deadline ASC
LIMIT 5;

// === Связанные сущности (транзитивные связи) ===

MATCH path = (e1:EntityNode {uuid: $entity_uuid})-[*1..3]-(e2:EntityNode)
WHERE e1 <> e2
RETURN DISTINCT e2.name, labels(e2)[0] AS entity_type, length(path) AS distance
ORDER BY distance ASC
LIMIT 10;

// === Проекты с приближающимся дедлайном ===

MATCH (p:Project {status: "active"})
WHERE p.deadline >= date()
AND p.deadline <= date() + duration({days: 30})
RETURN p.name, p.deadline, duration.inDays(date(), p.deadline).days AS days_left
ORDER BY days_left ASC;


// ============================================================================
// 8. MAINTENANCE (Очистка, обслуживание)
// ============================================================================

// === Удалить старые pending checks (> 30 дней) ===

MATCH (c:UserCheckStatus {status: 'pending'})
WHERE c.timestamp < datetime() - duration({days: 30})
DETACH DELETE c;

// === Архивировать завершенные проекты ===

MATCH (p:Project {status: "completed"})
WHERE p.completed_at < datetime() - duration({months: 6})
SET p.status = "archived", p.archived_at = datetime()
RETURN p.name, p.archived_at;

// === Посчитать общее количество нод по типам ===

MATCH (n)
RETURN labels(n)[0] AS label, count(n) AS count
ORDER BY count DESC;


// ============================================================================
// 9. TESTING QUERIES (для разработки)
// ============================================================================

// === Создать тестовую заметку с сущностями ===

CREATE (n:Note {
    path: "test/sample.md",
    created_at: datetime(),
    para_type: "Project"
})

CREATE (p1:EntityNode {
    uuid: "test_person_1",
    name: "John Smith",
    labels: ["Person"]
})

CREATE (p2:EntityNode {
    uuid: "test_org_1",
    name: "TechCorp",
    labels: ["Organization"]
})

CREATE (n)-[:CONTAINS]->(p1)
CREATE (n)-[:CONTAINS]->(p2)

CREATE (check1:UserCheckStatus {
    id: "test_check_1",
    status: "pending",
    confirmation_level: "entity",
    confidence: 0.85,
    timestamp: datetime()
})

CREATE (p1)-[:HAS_CHECK {is_current: true}]->(check1)

RETURN n, p1, p2, check1;

// === Очистить все тестовые данные ===

MATCH (n)
WHERE n.uuid STARTS WITH "test_" OR n.path STARTS WITH "test/"
DETACH DELETE n;


// ============================================================================
// КОНЕЦ ФАЙЛА
// ============================================================================
