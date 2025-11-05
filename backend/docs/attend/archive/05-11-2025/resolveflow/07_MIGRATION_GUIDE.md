# Руководство по Миграции: Обновление Существующих Заметок

**Дата**: 2025-10-27
**Контекст**: [05_IMPLEMENTATION_PLAN.md](./05_IMPLEMENTATION_PLAN.md)

---

## Обзор Миграции

После внедрения ранней PARA-классификации, существующие заметки в графе **не будут иметь PARA labels**. Это руководство описывает стратегии миграции старых заметок.

---

## Стратегии Миграции

### Вариант A: Постепенная (Lazy) Миграция

**Идея**: Не мигрировать сразу все заметки. Классифицировать только при повторной обработке.

**Плюсы**:
- Минимальная нагрузка на систему
- Бесплатно (не нужны LLM вызовы для всех заметок)
- Естественное обновление при редактировании заметок

**Cons**:
- Старые заметки остаются без PARA labels
- Несогласованный граф (часть с labels, часть без)

**Имплементация**: Уже работает out-of-the-box. Ничего делать не нужно.

---

### Вариант B: Полная Миграция (Batch Reprocessing)

**Идея**: Запустить скрипт, который классифицирует все существующие заметки.

**Плюсы**:
- Согласованный граф (все заметки с PARA labels)
- Сразу доступны улучшенные связи

**Cons**:
- Дорого (LLM вызов для каждой заметки)
- Время выполнения зависит от количества заметок
- Риск ошибок при batch processing

**Имплементация**: См. ниже секцию "Скрипт Миграции".

---

### Вариант C: Выборочная Миграция

**Идея**: Классифицировать только важные заметки (например, последние 3 месяца).

**Плюсы**:
- Баланс между стоимостью и пользой
- Фокус на актуальных данных

**Cons**:
- Требует критерии выбора (дата? частота обращений?)

**Имплементация**: Модификация скрипта миграции с фильтрами.

---

## Рекомендуемая Стратегия

**Гибридный подход**:
1. **Lazy миграция по умолчанию** (Вариант A)
2. **Опциональная полная миграция** (Вариант B) для пользователей, которые хотят

---

## Скрипт Полной Миграции

### Batch Classification Script

**File**: `backend/scripts/migrate_para_labels.py`

```python
"""
Migrate existing notes to add PARA labels.

Usage:
    python scripts/migrate_para_labels.py [--dry-run] [--limit N]

Options:
    --dry-run: Print what would be done without making changes
    --limit N: Only process N notes (for testing)
    --since DATE: Only process notes created after DATE (YYYY-MM-DD)
"""

import asyncio
import argparse
from datetime import datetime
from typing import Optional

from app.services.llm_graphiti_client import get_graphiti
from app.services.pipgraph_manager import PipGraphManager
from graphiti_core.nodes import EpisodicNode


async def migrate_para_labels(
    dry_run: bool = False,
    limit: Optional[int] = None,
    since: Optional[datetime] = None,
):
    """Migrate existing notes to add PARA labels."""

    print("🔄 Starting PARA label migration...")

    # Initialize services
    graphiti = await get_graphiti()
    manager = PipGraphManager(graphiti)

    # Fetch all episodes without PARA labels
    query = """
    MATCH (e:EpisodicNode)
    WHERE size(e.labels) = 0 OR NOT any(label IN e.labels WHERE label IN ['Project', 'Area', 'Resource', 'Archive'])
    """

    if since:
        query += f" AND e.created_at >= datetime('{since.isoformat()}')"

    query += " RETURN e.uuid as uuid, e.name as name, e.content as content"

    if limit:
        query += f" LIMIT {limit}"

    result = await graphiti.driver.execute_query(query)
    episodes = result.records

    print(f"📊 Found {len(episodes)} episodes to migrate")

    if dry_run:
        print("🔍 DRY RUN MODE - No changes will be made\n")

    migrated = 0
    skipped = 0
    errors = 0

    for i, episode in enumerate(episodes, 1):
        uuid = episode["uuid"]
        name = episode["name"]
        content = episode["content"] or ""

        print(f"\n[{i}/{len(episodes)}] Processing: {name}")

        try:
            # Classify note
            para_type, attrs, confidence = await manager.classify_note_as_para(
                episode_body=content,
                name=name,
            )

            if para_type is None:
                print(f"  ⏭️  Skipped (no clear PARA type, confidence: {confidence:.2f})")
                skipped += 1
                continue

            print(f"  ✅ Classified as: {para_type} (confidence: {confidence:.2f})")

            if not dry_run:
                # Update episode label in Neo4j
                await _update_episode_label(graphiti.driver, uuid, para_type, attrs)
                print(f"  💾 Updated label in database")

            migrated += 1

        except Exception as e:
            print(f"  ❌ Error: {e}")
            errors += 1

        # Rate limiting (avoid overwhelming LLM API)
        if i % 10 == 0:
            await asyncio.sleep(1)  # Brief pause every 10 notes

    # Summary
    print(f"\n" + "="*50)
    print(f"🎉 Migration {'simulation' if dry_run else 'complete'}!")
    print(f"✅ Migrated: {migrated}")
    print(f"⏭️  Skipped: {skipped}")
    print(f"❌ Errors: {errors}")
    print(f"📊 Total processed: {len(episodes)}")


async def _update_episode_label(driver, uuid: str, para_type: str, attributes: dict):
    """Update episode with PARA label and attributes."""

    query = """
    MATCH (e:EpisodicNode {uuid: $uuid})
    SET e.labels = [$para_type]
    SET e += $attributes
    RETURN e
    """

    await driver.execute_query(
        query,
        uuid=uuid,
        para_type=para_type,
        attributes=attributes,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate PARA labels")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without changes")
    parser.add_argument("--limit", type=int, help="Limit number of notes to process")
    parser.add_argument("--since", type=str, help="Only process notes created after DATE (YYYY-MM-DD)")

    args = parser.parse_args()

    since_date = None
    if args.since:
        since_date = datetime.fromisoformat(args.since)

    asyncio.run(migrate_para_labels(
        dry_run=args.dry_run,
        limit=args.limit,
        since=since_date,
    ))
```

---

### Usage Examples

#### Dry Run (Test First)

```bash
cd backend/
python scripts/migrate_para_labels.py --dry-run --limit 10
```

Output:
```
🔄 Starting PARA label migration...
📊 Found 10 episodes to migrate
🔍 DRY RUN MODE - No changes will be made

[1/10] Processing: Q4 Campaign
  ✅ Classified as: Project (confidence: 0.92)

[2/10] Processing: Team Management
  ✅ Classified as: Area (confidence: 0.87)

...

🎉 Migration simulation complete!
✅ Migrated: 8
⏭️  Skipped: 2
❌ Errors: 0
```

#### Migrate Recent Notes Only

```bash
python scripts/migrate_para_labels.py --since 2025-01-01
```

#### Full Migration (All Notes)

```bash
# Run without limits (be prepared for long execution and costs!)
python scripts/migrate_para_labels.py
```

---

## Selective Migration

### Query-Based Migration

For more control, use Neo4j Cypher queries:

```cypher
// Find all notes from specific folder
MATCH (e:EpisodicNode)
WHERE e.source_description CONTAINS 'Projects'
  AND size(e.labels) = 0
RETURN e.uuid, e.name
```

Then pass UUIDs to selective migration script.

---

### Priority-Based Migration

**Strategy**: Migrate notes by priority:
1. Recent notes (last 30 days)
2. Frequently accessed notes
3. Notes with many connections
4. All others

**File**: `backend/scripts/migrate_para_priority.py`

```python
"""Priority-based PARA migration."""

async def get_priority_notes(driver):
    """Get notes sorted by priority."""

    # Priority 1: Recent notes (last 30 days)
    recent_query = """
    MATCH (e:EpisodicNode)
    WHERE e.created_at >= datetime() - duration('P30D')
      AND size(e.labels) = 0
    RETURN e.uuid as uuid, e.name as name, e.content as content, 1 as priority
    """

    # Priority 2: Notes with many connections
    connected_query = """
    MATCH (e:EpisodicNode)
    WHERE size(e.labels) = 0
    WITH e, size((e)-[]->()) + size((e)<-[]-()) as connection_count
    WHERE connection_count > 5
    RETURN e.uuid as uuid, e.name as name, e.content as content, 2 as priority
    ORDER BY connection_count DESC
    """

    # Combine and sort by priority
    # ... implementation ...
```

---

## Monitoring Migration

### Progress Tracking

**Neo4j Query** to check migration progress:

```cypher
// Count notes by PARA type
MATCH (e:EpisodicNode)
RETURN
  CASE
    WHEN 'Project' IN e.labels THEN 'Project'
    WHEN 'Area' IN e.labels THEN 'Area'
    WHEN 'Resource' IN e.labels THEN 'Resource'
    WHEN 'Archive' IN e.labels THEN 'Archive'
    ELSE 'Unclassified'
  END as para_type,
  count(*) as count
ORDER BY count DESC
```

**Expected Output**:
```
para_type       | count
----------------|------
Unclassified    | 1500  ← Decreases as migration progresses
Project         | 120
Area            | 45
Resource        | 230
Archive         | 30
```

---

### Migration Dashboard (Optional)

Create monitoring dashboard:

```python
# scripts/monitor_migration.py

async def migration_dashboard():
    """Display migration progress dashboard."""

    graphiti = await get_graphiti()

    # Count by type
    query = """
    MATCH (e:EpisodicNode)
    RETURN
      CASE
        WHEN 'Project' IN e.labels THEN 'Project'
        WHEN 'Area' IN e.labels THEN 'Area'
        WHEN 'Resource' IN e.labels THEN 'Resource'
        WHEN 'Archive' IN e.labels THEN 'Archive'
        ELSE 'Unclassified'
      END as type,
      count(*) as count
    """

    result = await graphiti.driver.execute_query(query)

    print("\n📊 PARA Migration Dashboard")
    print("="*40)
    for record in result.records:
        print(f"{record['type']:15} | {record['count']:5}")

    total = sum(r["count"] for r in result.records)
    unclassified = next((r["count"] for r in result.records if r["type"] == "Unclassified"), 0)
    migrated_pct = ((total - unclassified) / total * 100) if total > 0 else 0

    print("="*40)
    print(f"Migration Progress: {migrated_pct:.1f}%")
```

---

## Cost Estimation

### LLM API Costs

**Assumptions**:
- Model: gpt-4o-mini
- Avg tokens per classification: ~1500 tokens (input) + 200 tokens (output)
- Cost: $0.15/1M input tokens, $0.60/1M output tokens

**Calculation**:
```
Cost per note = (1500 * $0.15 / 1M) + (200 * $0.60 / 1M)
              = $0.000225 + $0.00012
              = ~$0.00034 per note
```

**For 1000 notes**: ~$0.34
**For 10,000 notes**: ~$3.40

**Recommendation**: Start with recent notes to control costs.

---

## Rollback Strategy

If migration causes issues:

### Option 1: Remove PARA Labels

```cypher
// Remove all PARA labels from episodes
MATCH (e:EpisodicNode)
WHERE any(label IN e.labels WHERE label IN ['Project', 'Area', 'Resource', 'Archive'])
SET e.labels = []
```

### Option 2: Restore from Backup

Before running migration:
```bash
# Backup Neo4j database
neo4j-admin dump --database=neo4j --to=/backup/neo4j-backup-$(date +%Y%m%d).dump
```

After issues:
```bash
# Restore from backup
neo4j-admin load --database=neo4j --from=/backup/neo4j-backup-YYYYMMDD.dump --force
```

---

## Best Practices

1. **Always dry-run first**: Test on small subset
2. **Monitor costs**: Start with recent notes (--since flag)
3. **Backup database**: Before full migration
4. **Rate limit**: Avoid overwhelming LLM API
5. **Validate results**: Spot-check classifications
6. **Incremental approach**: Migrate in batches of 100-500 notes
7. **Off-peak timing**: Run during low-usage periods

---

## FAQ

**Q: Do I need to migrate existing notes?**

A: No. Old notes without PARA labels will continue to work. Migration is optional for improved organization and search.

---

**Q: Will migration overwrite existing data?**

A: No. Migration only adds PARA labels to episodes that don't have them. Existing content, entities, and relationships are preserved.

---

**Q: What happens if migration fails midway?**

A: The script processes notes one-by-one. Already migrated notes won't be reprocessed (they have labels). You can safely re-run the script to continue.

---

**Q: Can I migrate specific folders only?**

A: Yes. Modify the script's query to filter by `source_description` or other criteria.

---

**Q: How long does full migration take?**

A: Depends on:
- Number of notes
- LLM API speed (~1-2 sec per note)
- Rate limiting

Estimate: ~1000 notes = 30-60 minutes

---

## Verification Checklist

After migration:

- [ ] Run dashboard to check progress
- [ ] Verify sample of classifications manually
- [ ] Check that old functionality still works
- [ ] Test search with PARA filters
- [ ] Confirm edge enrichment on migrated notes
- [ ] Monitor for errors in logs
- [ ] Validate cost vs. estimate

---

## Support

If migration issues occur:
1. Check logs: `backend/logs/migration.log`
2. Run verification queries (see Monitoring section)
3. Consult error messages in script output
4. Consider rollback if critical issues

---

## Summary

**Recommended Migration Path**:
1. Test with dry-run (--dry-run --limit 10)
2. Migrate recent notes (--since 2025-01-01)
3. Validate results
4. Gradually expand to older notes
5. Monitor progress and costs

**Don't forget**: Lazy migration works well for most use cases. Full migration is optional!
