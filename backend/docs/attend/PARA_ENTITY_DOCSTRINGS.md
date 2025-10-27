# PARA Entity Types: LLM-Optimized Docstrings

## Назначение документа

Этот документ содержит подробные docstring-описания для высокоуровневых PARA entity типов, оптимизированные для использования LLM при извлечении сущностей и классификации заметок. Эти промпты помогают языковой модели правильно определить, к какому типу PARA относится заметка целиком или её отдельные части.

## Принципы создания промптов

1. **Контекстная специфичность**: Описания содержат конкретные маркеры, по которым LLM может идентифицировать тип
2. **Разграничение типов**: Явно указаны отличия между похожими типами (например, Project vs Area)
3. **Примеры использования**: Встроенные примеры помогают LLM понять контекст применения
4. **Lifecycle-ориентированность**: Описан жизненный цикл каждого типа сущности

---

## PARA Entity Type Definitions

### 1. Project

```python
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class Project(BaseModel):
    """
    A Project is a time-bound initiative with a specific, achievable goal and a clear deadline.

    IDENTIFICATION CRITERIA for LLM:
    - Has a concrete, measurable outcome or deliverable
    - Contains explicit or implicit deadline/timeframe (e.g., "launch by Q4", "due next month")
    - Represents active work towards a specific objective
    - Will have a definite completion state (done/not done)
    - Often contains action items, milestones, or progress tracking

    EXAMPLES of Project notes:
    - "Launch marketing campaign for Product X by December 2024"
    - "Prepare presentation for TechConf 2025"
    - "Website redesign project - Q1 2024"
    - "Write research paper on quantum computing (deadline: March 15)"

    NOT a Project if:
    - No clear endpoint (e.g., "Health and fitness" - this is an Area)
    - Pure reference material (e.g., "Python best practices" - this is a Resource)
    - Already completed and archived (this becomes Archive state)
    - Ongoing responsibility without specific goal (e.g., "Team management" - this is an Area)

    LIFECYCLE:
    When a project is completed, its status changes to 'completed' or 'archived',
    and related ContentBlocks may be relinked to Areas or Resources for long-term knowledge retention.
    """

    name: str = Field(
        ...,
        description="The project title - should be specific and action-oriented (e.g., 'Launch Q4 Marketing Campaign', not just 'Marketing')"
    )

    status: str = Field(
        default="active",
        description="""
        Current project state. Values: 'active' (in progress), 'completed' (goal achieved),
        'on_hold' (temporarily paused), 'cancelled' (abandoned), 'archived' (completed and moved to archive).
        Default is 'active' for new projects.
        """
    )

    deadline: Optional[datetime] = Field(
        None,
        description="""
        The target completion date or deadline. Extract from phrases like:
        'by December', 'due on 2024-03-15', 'before Q2', 'launch date: Jan 1st'.
        If only month/year mentioned, use end of that period.
        """
    )

    goal: Optional[str] = Field(
        None,
        description="""
        The specific, measurable objective or desired outcome. Extract the concrete result, not the process.
        Examples: 'Increase user signups by 20%', 'Publish paper in peer-reviewed journal',
        'Complete all product certifications'.
        """
    )

    completion_criteria: Optional[str] = Field(
        None,
        description="""
        How to determine if the project is done. Look for phrases like:
        'success criteria', 'definition of done', 'deliverables', 'acceptance criteria'.
        """
    )
```

---

### 2. Area

```python
class Area(BaseModel):
    """
    An Area represents an ongoing sphere of responsibility, activity, or interest that requires
    continuous attention and maintenance, but has no endpoint.

    IDENTIFICATION CRITERIA for LLM:
    - Represents a role, responsibility, or life domain that continues indefinitely
    - Contains standards, best practices, or guidelines to maintain
    - No specific deadline or completion state
    - Requires regular review and updates
    - Often organized around themes like health, relationships, career, finances

    EXAMPLES of Area notes:
    - "Personal Health and Fitness" (ongoing responsibility)
    - "Team Management" (continuous role)
    - "Financial Planning" (long-term concern)
    - "Home Maintenance" (recurring duties)
    - "Professional Development" (continuous improvement)
    - "Family Relationships" (ongoing care)

    NOT an Area if:
    - Has a specific deadline (e.g., "Learn Spanish by June" - this is a Project)
    - Pure reference info with no action required (e.g., "Spanish grammar rules" - this is a Resource)
    - One-time goal (e.g., "Buy a house" - this is a Project)
    - Not personally responsible (e.g., "History of Rome" - this is a Resource)

    RELATIONSHIP WITH PROJECTS:
    Areas often spawn Projects. For example, the Area "Health" might generate Projects like
    "Complete marathon training by October" or "Lose 10kg by summer". When a project completes,
    learnings return to the parent Area.

    STANDARDS AND MAINTENANCE:
    Areas are where you define 'how things should be' in different parts of your life.
    They contain standards, checklists, SOPs, and accumulated wisdom.
    """

    name: str = Field(
        ...,
        description="""
        The area title - should represent a domain or responsibility, not a specific goal.
        Use nouns/gerunds: 'Health', 'Team Leadership', 'Product Management', not action verbs.
        """
    )

    goal: Optional[str] = Field(
        None,
        description="""
        The desired standard or aspirational state for this area (not a time-bound goal).
        Examples: 'Maintain excellent physical fitness', 'Be an effective and supportive leader',
        'Keep financial stability and growth', 'Nurture meaningful family connections'.
        Use present tense or 'maintain/nurture/develop' language.
        """
    )

    review_frequency: Optional[str] = Field(
        None,
        description="""
        How often this area should be reviewed or maintained. Extract from phrases like:
        'weekly review', 'monthly check-in', 'quarterly assessment', 'daily practice'.
        """
    )

    responsibilities: Optional[list[str]] = Field(
        None,
        description="""
        Key ongoing duties or standards within this area. Extract bullet points, checklists,
        or recurring tasks mentioned. Each item should be a continuous responsibility, not a one-time task.
        """
    )

    success_indicators: Optional[list[str]] = Field(
        None,
        description="""
        Metrics or signals that indicate this area is healthy/successful. Look for:
        'KPIs', 'health metrics', 'signs of success', 'what good looks like'.
        Examples: 'Team satisfaction score >4.0', 'Exercise 3x per week', 'Zero critical bugs in production'.
        """
    )
```

---

### 3. Resource

```python
class Resource(BaseModel):
    """
    A Resource is a collection of reference material on a topic of interest that you want to
    learn about or refer to in the future, but which doesn't require immediate action or ongoing responsibility.

    IDENTIFICATION CRITERIA for LLM:
    - Contains information, knowledge, or reference material
    - No deadline or completion state
    - No personal responsibility or obligation implied
    - Used for learning, inspiration, or future reference
    - Often includes: guides, tutorials, curated links, research notes, how-tos, concepts
    - Passive consumption rather than active management

    EXAMPLES of Resource notes:
    - "Introduction to Quantum Computing" (learning material)
    - "Best Practices for API Design" (reference guide)
    - "Recipes: Italian Cuisine" (curated collection)
    - "History of Byzantine Empire" (interest topic)
    - "Rust Programming Language Resources" (learning materials)
    - "Stoic Philosophy Principles" (conceptual knowledge)

    NOT a Resource if:
    - Requires action or decisions (e.g., "Choose new health insurance" - this is a Project)
    - Ongoing responsibility (e.g., "Maintain coding skills" - this is an Area)
    - Time-bound learning goal (e.g., "Master React by Q2" - this is a Project)

    PURPOSE:
    Resources are your personal knowledge library and learning materials. They're meant to be
    referenced when needed, browsed for inspiration, or used as source material for Projects and Areas.

    ORGANIZATION:
    Resources are typically organized by topic, subject, or theme. They can be linked to Projects
    (as reference material) or Areas (as knowledge base), but exist independently.
    """

    topic: str = Field(
        ...,
        description="""
        The subject or theme of this resource. Should be a clear topic area, not a project goal.
        Examples: 'Machine Learning', 'Stoic Philosophy', 'Mediterranean Cooking',
        'TypeScript Programming', 'Ancient Roman History'.
        """
    )

    description: Optional[str] = Field(
        None,
        description="""
        A brief summary of what this resource covers or why it's valuable.
        Extract from introductory paragraphs or explicit descriptions.
        Focus on 'what is this about' not 'what should I do with this'.
        """
    )

    category: Optional[str] = Field(
        None,
        description="""
        The type or category of resource. Look for or infer from content type:
        'Tutorial', 'Reference Guide', 'Research Notes', 'Curated Links', 'Book Notes',
        'Concept Explanation', 'How-To Guide', 'Case Studies', 'Examples Collection'.
        """
    )

    tags: Optional[list[str]] = Field(
        None,
        description="""
        Relevant keywords or themes for this resource. Extract explicit tags or infer from:
        - Technical topics (e.g., 'python', 'API', 'database')
        - Domains (e.g., 'health', 'finance', 'productivity')
        - Resource type (e.g., 'video', 'article', 'book')
        Keep tags concise and consistent.
        """
    )

    source_type: Optional[str] = Field(
        None,
        description="""
        The format or medium of the resource. Extract or infer:
        'article', 'book', 'video', 'course', 'documentation', 'podcast',
        'research paper', 'blog post', 'wiki', 'notes', 'curated collection'.
        """
    )

    last_reviewed: Optional[datetime] = Field(
        None,
        description="""
        When this resource was last reviewed or updated. Look for:
        'last updated', 'reviewed on', 'as of', metadata timestamps.
        Helps track resource freshness.
        """
    )
```

---

### 4. Archive

```python
class Archive(BaseModel):
    """
    Archive represents completed, inactive, or no-longer-relevant Projects, Areas, or Resources
    that are preserved for historical reference but removed from active view.

    IMPORTANT: Archive is more of a STATE than a distinct entity type. It's implemented by:
    - Changing the 'status' field of a Project to 'completed' or 'archived'
    - Marking an Area or Resource as 'archived'
    - Maintaining graph relationships but flagging nodes as inactive

    IDENTIFICATION CRITERIA for LLM:
    - Explicitly marked as completed, finished, or archived
    - Contains past-tense language about goals or activities
    - Metadata indicates old dates (e.g., "Project completed 2 years ago")
    - Note contains retrospective content (e.g., "Lessons learned", "Post-mortem")

    EXAMPLES of Archive content:
    - "Q3 2022 Marketing Campaign - Completed" (finished project)
    - "Old Home Maintenance Guidelines (moved to new house)" (obsolete area)
    - "Python 2.7 Tutorial (deprecated)" (outdated resource)
    - "Completed: Website Redesign Project (Launched Dec 2023)"

    WHY ARCHIVE (not delete):
    - Preserve institutional knowledge and learnings
    - Enable historical search and reference
    - Track patterns and progress over time
    - Maintain context for related active items

    ARCHIVAL TRIGGERS:
    - Project deadline passed and goal achieved/abandoned
    - Area no longer relevant due to life changes
    - Resource outdated or superseded by better information
    - Explicitly marked by user as "archive", "completed", or "inactive"

    IMPLEMENTATION NOTE:
    Instead of creating Archive entity nodes, we typically:
    1. Update status field of original entity (Project.status = 'archived')
    2. Add archived_at timestamp
    3. Optionally preserve outcome or lessons learned
    4. Filter out archived items from default queries (but keep searchable)
    """

    original_type: str = Field(
        ...,
        description="""
        What type of entity this was before archival: 'Project', 'Area', or 'Resource'.
        This helps understand the context and lifecycle of the archived item.
        """
    )

    original_name: str = Field(
        ...,
        description="""
        The original name/title of the Project, Area, or Resource.
        Preserve exactly as it was when active.
        """
    )

    archived_at: datetime = Field(
        ...,
        description="""
        When this item was archived. Extract from:
        - Explicit 'archived on' statements
        - Project completion dates
        - 'last modified' timestamps if explicitly inactive
        - Use current date if archival is implied but not dated
        """
    )

    archival_reason: Optional[str] = Field(
        None,
        description="""
        Why this was archived. Common reasons:
        - 'Project completed successfully'
        - 'Project cancelled or abandoned'
        - 'Area no longer relevant (life change)'
        - 'Resource outdated or superseded'
        - 'Moved to different system'
        Extract from retrospective language or explicit statements.
        """
    )

    outcome: Optional[str] = Field(
        None,
        description="""
        For completed Projects: what was achieved or learned.
        Look for: 'Results:', 'Outcome:', 'Lessons learned:', 'Retrospective:', 'What happened:'.
        Captures the value of preserving this archived item.
        """
    )

    status: str = Field(
        default="archived",
        description="""
        Always 'archived' for Archive entities. This field exists for consistency
        with other PARA types and to enable potential sub-states like 'permanently_archived'.
        """
    )
```

---

## Использование этих моделей

### 1. Передача в Graphiti

```python
from datetime import datetime
from graphiti_core import Graphiti

# Импорт моделей PARA
from app.models.para_entities import Project, Area, Resource, Archive

# Определение типов сущностей для Graphiti
entity_types = {
    "Project": Project,
    "Area": Area,
    "Resource": Resource,
    "Archive": Archive,
}

# Использование при добавлении эпизода
await graphiti.add_episode(
    name="My Obsidian Note - Project Planning.md",
    episode_body=note_content,
    source_description="Obsidian note from Projects folder",
    reference_time=datetime.now(),
    entity_types=entity_types,
)
```

### 2. Классификация заметки целиком

При обработке заметки LLM будет:
1. Анализировать содержимое на основе docstrings
2. Искать маркеры идентификации (дедлайны, обязанности, справочная информация)
3. Определять основной тип PARA для всей заметки
4. Создавать узел соответствующего типа в графе
5. Связывать ContentBlock'и с этим высокоуровневым узлом через IS_PART_OF

### 3. Обработка смешанного контента

Если заметка содержит элементы разных типов (например, Project с Resource-секцией):
- Основная заметка классифицируется как Project (доминирующий тип)
- Отдельные ContentBlock'и могут иметь связи с Resource узлами
- LLM использует контекст и структуру для определения приоритета

---

## Рекомендации для разработчиков

### Улучшение промптов

1. **Добавьте примеры из вашего домена**: Если ваши пользователи работают в специфической области (медицина, юриспруденция, разработка), добавьте доменные примеры в docstrings.

2. **Уточните граничные случаи**: Если LLM путает Project и Area в вашем контексте, добавьте специфичные контр-примеры в секцию "NOT a X if...".

3. **Используйте Field descriptions как микро-промпты**: Каждое поле - это отдельная инструкция для LLM. Чем конкретнее, тем лучше извлечение.

### Тестирование классификации

```python
# Создайте тестовые заметки с явным типом
test_cases = [
    ("Launch new blog by March", "Project"),  # has deadline
    ("Maintain physical health", "Area"),     # ongoing responsibility
    ("Python async programming guide", "Resource"),  # reference material
]

# Проверьте, что LLM классифицирует корректно
for note_text, expected_type in test_cases:
    result = await graphiti.add_episode(...)
    # Verify extracted entity has correct label
    assert result.entity_type == expected_type
```

### Мониторинг качества

- Логируйте случаи, когда LLM не может определить тип (confidence < threshold)
- Анализируйте ошибки классификации и обновляйте docstrings
- Собирайте feedback пользователей о неправильно классифицированных заметках

---

## Дальнейшее развитие

### Потенциальные расширения

1. **Подтипы**: Можно добавить подтипы для более точной классификации
   - `ProjectType`: "personal", "professional", "creative"
   - `AreaType`: "health", "relationships", "career", "finance"

2. **Мета-атрибуты**: Добавить поля для улучшения управления
   - `priority`: "high", "medium", "low"
   - `energy_level`: "high-energy", "low-energy" (GTD-стиль)
   - `complexity`: "simple", "moderate", "complex"

3. **Связи между PARA типами**:
   - `(Project) -[:CONTRIBUTES_TO]-> (Area)`
   - `(Project) -[:USES]-> (Resource)`
   - `(Area) -[:SPAWNED]-> (Project)`

4. **Темпоральная логика**: Автоматическая архивация на основе deadline
   ```python
   if project.deadline < datetime.now() and project.status == "active":
       project.status = "archived"
       project.archived_at = datetime.now()
   ```

---

## Выводы

Эти docstrings предназначены для:
- ✅ Помощи LLM в точной классификации заметок
- ✅ Обеспечения консистентности извлечения данных
- ✅ Документирования архитектурных решений
- ✅ Обучения новых разработчиков методу PARA

Регулярно пересматривайте и обновляйте промпты на основе реальных данных о качестве классификации.
