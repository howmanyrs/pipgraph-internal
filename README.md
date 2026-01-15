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

## Архитектура

PipGraph построен как монорепозиторий из трех компонентов:

- **backend/** — Python FastAPI сервер с REST API, LLM интеграцией и Neo4j
- **pipgraph-web/** — Next.js веб-интерфейс для управления графом знаний
- **obsidian-plugin/** — TypeScript плагин для Obsidian (в разработке)

Все компоненты взаимодействуют через REST API. Backend обрабатывает заметки с помощью LLM, извлекает сущности и сохраняет их в графовую базу Neo4j.

**Детали архитектуры:** См. `backend/CLAUDE.md` и `pipgraph-web/CLAUDE.md`

## Методология PARA

Система организует знания по методологии PARA (Tiago Forte):

- **Projects** — краткосрочные цели с дедлайнами
- **Areas** — долгосрочные зоны ответственности
- **Resources** — темы постоянного интереса
- **Archives** — неактивные элементы
- **Inbox** — дефолтная зона для новых заметок

## Быстрый старт

**Требования:** Python 3.12+, Node.js 18+, Neo4j

1. **Backend:**
   ```bash
   cd backend/
   uv venv && source .venv/bin/activate
   uv pip install -r requirements.txt
   cp .env.example .env  # Настроить API ключи
   uvicorn app.api.main:app --reload
   ```

2. **Web UI:**
   ```bash
   cd pipgraph-web/
   npm install
   npm run dev
   ```

3. **Neo4j:** Запустить через Neo4j Desktop или Docker

**Детали установки:** См. `backend/CLAUDE.md` и `pipgraph-web/CLAUDE.md`

## Документация

- **[CLAUDE.md](CLAUDE.md)** — Краткая справка для Claude Code
- **[backend/CLAUDE.md](backend/CLAUDE.md)** — Backend quick reference
- **[pipgraph-web/CLAUDE.md](pipgraph-web/CLAUDE.md)** — Web UI quick reference
- **[backend/docs/](backend/docs/)** — Подробные технические документы

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


---

**Для Claude Code:** Это основной README. Для быстрой справки см. [CLAUDE.md](CLAUDE.md). Для специфичных компонентов см. `backend/CLAUDE.md` и `pipgraph-web/CLAUDE.md`.
