# PipGraph — Intelligent Knowledge Graph System

**Статус:** В активной разработке
**Дата обновления:** 13.01.2026

## Обзор проекта

PipGraph — это система для преобразования неструктурированных заметок Markdown (Obsidian) в структурированный граф знаний с использованием LLM. Проект реализует философию "второго мозга" с поддержкой методологии PARA (Projects, Areas, Resources, Archives) от Tiago Forte.

**Ключевые принципы:**
- **Неразрушающая обработка:** Контент заметок остается неизменным, метаданные пишутся только в YAML frontmatter
- **Graph-First архитектура:** Знания хранятся как граф (узлы + связи) в Neo4j
- **Human-in-the-Loop:** Система предлагает, пользователь решает
- **REST API:** Прямой доступ к функциям через FastAPI эндпоинты

## Архитектура системы

```
┌─────────────────────────────────────────────────────────────┐
│                    FRONTEND CLIENTS                          │
├──────────────────┬────────────────────┬─────────────────────┤
│ pipgraph-web     │ obsidian-plugin    │ Direct API Access   │
│ (Next.js 16)     │ (в разработке)     │ (curl/Python SDK)   │
│ • TanStack Query │ • TypeScript       │                     │
│ • shadcn/ui      │ • Svelte           │                     │
│ • Rapid Proto    │ • WebSocket client │                     │
└──────────────────┴────────────────────┴─────────────────────┘
                            │
                            │ REST API (HTTP/JSON)
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                      BACKEND (Python)                        │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ API Layer (FastAPI)                                    │ │
│  │ • /api/v1/dev/* endpoints                              │ │
│  │ • Pydantic validation                                  │ │
│  └────────────────────────────────────────────────────────┘ │
│                            │                                 │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ Service Layer                                          │ │
│  │ • PipGraphManager (single source of truth)             │ │
│  │ • LLM orchestration (OpenRouter/OpenAI)                │ │
│  │ • Entity extraction                                    │ │
│  │ • Hybrid search (BM25 + vector)                        │ │
│  └────────────────────────────────────────────────────────┘ │
│                            │                                 │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ Data Access Layer                                      │ │
│  │ • Graphiti integration                                 │ │
│  │ • Neo4j Cypher queries                                 │ │
│  │ • CRUD operations                                      │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
                    ┌───────────────┐
                    │    Neo4j      │
                    │  Graph DB     │
                    └───────────────┘
```

## Структура монорепозитория

```
pipgraph/
├── backend/                 # Python FastAPI бэкенд (основной компонент)
│   ├── app/
│   │   ├── api/            # REST эндпоинты
│   │   │   ├── endpoints/  # Роутеры (/dev, /search, etc.)
│   │   │   └── schemas/    # Pydantic request/response модели
│   │   ├── services/       # Бизнес-логика
│   │   │   └── graphiti/   # PipGraphManager — единая точка входа в БД
│   │   ├── crud/           # Neo4j CRUD операции
│   │   └── models/         # Доменные Pydantic модели
│   ├── tests/              # Unit/Integration/E2E тесты
│   ├── docs/               # Подробная документация
│   │   ├── CONFIGURATION.md
│   │   └── TESTING.md
│   ├── CLAUDE.md           # Быстрая справка для Claude Code
│   ├── TODO.md             # Трекинг задач
│   └── CHANGELOG.md        # История версий
│
├── pipgraph-web/           # Next.js веб-интерфейс (NEW)
│   ├── src/
│   │   ├── app/            # Next.js App Router
│   │   ├── components/     # React компоненты (shadcn/ui)
│   │   ├── lib/            # Утилиты
│   │   └── hooks/          # Custom React hooks
│   ├── CLAUDE.md           # Документация для разработки
│   └── package.json        # npm зависимости
│
├── obsidian-plugin/        # Obsidian плагин (в разработке)
│   └── ...                 # TypeScript, Svelte
│
├── CLAUDE.md               # Корневая справка для Claude Code
└── README.md               # Этот файл
```

## Технологический стек

### Backend
- **Runtime:** Python 3.12+
- **Framework:** FastAPI, Uvicorn
- **Database:** Neo4j (графовая БД)
- **LLM Integration:** Graphiti, LangGraph
- **Package Manager:** `uv`
- **Testing:** pytest (unit/integration/e2e)
- **Type Safety:** Pydantic, strict typing

### Frontend (pipgraph-web)
- **Framework:** Next.js 16.1.1 (App Router, React 19)
- **Language:** TypeScript (strict mode)
- **Styling:** Tailwind CSS v4, shadcn/ui (New York style)
- **State Management:** TanStack Query v5 (server state)
- **Form Validation:** React Hook Form + Zod
- **Content Rendering:** react-markdown v10

### Frontend (obsidian-plugin, в разработке)
- **Framework:** TypeScript, Svelte
- **API Client:** REST fetch/axios

## Быстрый старт

### 1. Установка зависимостей

**Требования:**
- Python 3.12+
- Node.js 18+
- Neo4j Desktop (или Docker)
- `uv` (Python package manager): `pip install uv`

### 2. Настройка Backend

```bash
cd backend/

# Создать виртуальное окружение
uv venv && source .venv/bin/activate  # Linux/Mac
# или .\.venv\Scripts\activate         # Windows

# Установить зависимости
uv pip install -r requirements.txt

# Настроить .env файл
cp .env.example .env
# Отредактировать .env: OPENROUTER_API_KEY, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

# Запустить сервер
uvicorn app.api.main:app --reload
# Сервер доступен на http://localhost:8000
# Swagger docs: http://localhost:8000/docs
```

### 3. Настройка pipgraph-web

```bash
cd pipgraph-web/

# Установить зависимости
npm install

# Настроить .env.local (опционально)
# NEXT_PUBLIC_API_URL=http://localhost:8000

# Запустить dev сервер
npm run dev
# Web UI доступен на http://localhost:3000
```

### 4. Запуск Neo4j

```bash
# Через Neo4j Desktop (рекомендуется):
# 1. Создать новый проект
# 2. Создать локальную БД (по умолчанию bolt://localhost:7687)
# 3. Запустить БД

# Или через Docker:
docker run \
  --name neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/your_password \
  neo4j:latest
```

## Ключевые API эндпоинты

Все функции доступны через `/api/v1/dev`:

| Method | Endpoint | Описание |
|--------|----------|----------|
| POST | `/dev/process-note` | Полная обработка заметки с LLM |
| POST | `/dev/process-existing-episode` | Переобработка существующего episodic |
| GET | `/dev/episodic?uuid={uuid}` | Получить episodic по UUID |
| GET | `/dev/episodic?name={name}` | Получить episodic по имени |
| GET | `/dev/episodics` | Список всех episodics |
| POST | `/dev/create-episode` | Создать легковесный episodic |
| POST | `/dev/para-entity` | Создать PARA сущность |
| GET | `/dev/para-entities` | Список PARA сущностей |
| POST | `/dev/link-entity-episode` | Связать сущность с episodic |
| POST | `/dev/make-suggestions` | Гибридный поиск релевантных сущностей |

**Детали:** См. `backend/app/api/endpoints/dev.py`

## Методология PARA

Система организует знания по методологии PARA:

- **Projects** — краткосрочные цели с дедлайнами
- **Areas** — долгосрочные зоны ответственности
- **Resources** — темы постоянного интереса
- **Archives** — неактивные элементы
- **Inbox** — дефолтная зона для новых заметок

## Модель данных (Neo4j)

### Узлы

**Episodic** (заметка):
```cypher
(:Episodic {
  uuid: "...",
  name: "path/to/note.md",
  content: "...",
  created_at: "...",
  valid_at: "..."
})
```

**PARA Entity**:
```cypher
(:Entity:Project|:Area|:Resource|:Archive {
  uuid: "...",
  name: "Project Alpha",
  summary: "...",
  name_embedding: [...],
  attributes: {...},
  created_at: "..."
})
```

### Связи

- `(:Episodic)-[:MENTIONS]->(:Entity)` — эпизод упоминает сущность
- `(:Entity)-[:RELATES_TO]->(:Entity)` — связь между сущностями

## Тестирование

```bash
cd backend/

# Быстрые unit-тесты (без внешних зависимостей)
pytest -m unit

# Integration тесты (требуют Neo4j, OpenRouter)
pytest -m integration

# Исключить медленные LLM-вызовы
pytest -m "not slow"

# Запустить все тесты
pytest
```

**Подробности:** См. `backend/docs/TESTING.md`

## Документация

### Для разработчиков
- **[CLAUDE.md](CLAUDE.md)** — Краткая справка для Claude Code
- **[backend/CLAUDE.md](backend/CLAUDE.md)** — Backend quick reference
- **[pipgraph-web/CLAUDE.md](pipgraph-web/CLAUDE.md)** — Web UI quick reference
- **[backend/docs/](backend/docs/)** — Подробные технические документы

### Для пользователей
- **[backend/TODO.md](backend/TODO.md)** — Roadmap и текущие задачи
- **[backend/CHANGELOG.md](backend/CHANGELOG.md)** — История изменений

## Текущий статус разработки

### ✅ Готово
- Backend REST API (`/api/v1/dev`)
- PipGraphManager (единая точка доступа к БД)
- Entity extraction через LLM
- Hybrid search (BM25 + vector embeddings)
- PARA classification
- pipgraph-web базовая структура (Next.js + TanStack Query)

### 🚧 В разработке
- pipgraph-web UI компоненты (Inbox, PARA management)
- Obsidian плагин интеграция
- Natural language search (NL-to-Cypher)

### 📋 В планах
- Real-time синхронизация с Obsidian
- Advanced graph visualizations
- Multi-user support

## Контрибьюция

Проект находится в активной исследовательской стадии. Архитектура может меняться.

**Перед коммитом:**
1. Запустите тесты: `pytest -m unit`
2. Проверьте type hints: `mypy app/`
3. Отформатируйте код: `black .` и `isort .`

## Лицензия

[Указать лицензию]

## Контакты

[Указать контакты]

---

**Для Claude Code:** Это основной README. Для быстрой справки см. [CLAUDE.md](CLAUDE.md). Для специфичных компонентов см. `backend/CLAUDE.md` и `pipgraph-web/CLAUDE.md`.
