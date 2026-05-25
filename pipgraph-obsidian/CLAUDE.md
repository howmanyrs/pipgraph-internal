# PipGraph Obsidian Plugin — Direction & Environment

> **Status: pre-implementation.** This document describes *where this component sits*, *what it is meant to do*, and *what is known about the surrounding environment*. Concrete technical decisions (APIs, libraries, UI patterns, file layouts) are intentionally **not** captured here — they live, evolving, under [`.docs/suggestions/`](./.docs/suggestions).

## What this is

`pipgraph-obsidian` is the **Obsidian plugin** in the PipGraph monorepo. It is a thin client over the PipGraph backend (see [`../backend`](../backend)) — analogous in role to [`../pipgraph-web`](../pipgraph-web), but embedded inside the user's Obsidian vault rather than delivered through a browser.

The plugin is being built **iteratively**. Expect frequent direction changes, throwaway prototypes, and research-driven course corrections. Treat any code as provisional until clearly marked otherwise.

## Why Obsidian, and what role does it play

Obsidian is the user's **native authoring environment** for notes. The plugin does **not** try to replace Obsidian's UI; instead it leans on what Obsidian already does well:

- **File explorer + folders** — the user's PARA structure (Projects / Areas / Resources / Archives) lives as folders. Notes are visible, organisable, and searchable through Obsidian's own widgets.
- **Tags, links, frontmatter** — notes get *enriched* (tags, links to PARA entities, embeddings) but the body of the note stays untouched. The backend already follows a non-destructive policy; the plugin must respect it.
- **Native editor, search, graph, hotkeys, mobile clients** — all of these are reused as-is.

PipGraph's plugin contributes **one missing capability**: a dedicated panel that helps the user **triage their inbox of unprocessed notes** using LLM-suggested placements. This is the centre of the design problem.

## The core design problem (the hard part)

The user dumps notes into an inbox folder. PipGraph's backend can suggest, for each note, which PARA entity / folder it most likely belongs to (via hybrid search + LLM). The question this plugin must answer is:

> **How does the user efficiently confirm, correct, or reject these suggestions, in a way that feels like GTD inbox processing rather than another database UI?**

There is an additional, more subtle subproblem:

> **The most informative way to show a suggestion is to *place* the note in its proposed folder — so the user sees it in context. But the user must immediately be able to tell which notes landed there by a human decision vs. by an automatic suggestion that still needs confirmation.**

This requires some kind of visual "tentative / pending review" indicator on the file-explorer entry itself. Whether that is feasible — and how — is a research question. See [`.docs/suggestions/`](./.docs/suggestions).

## Where this plugin sits in the monorepo

```
pipgraph/
├── backend/           # FastAPI service — single source of truth for graph state
├── pipgraph-web/      # Next.js web client (rapid prototyping UI)
├── pipgraph-obsidian/ # ← this plugin (in-vault UI for triage + enrichment)
└── obsidian-plugin/   # ← earlier exploratory plugin (legacy / reference only)
```

Important: the plugin is a **client of the backend REST API** — it must not talk to Neo4j directly, must not embed LLM logic, and must not duplicate `PipGraphManager` responsibilities. Everything that touches the graph goes through `backend/app/api/endpoints/dev.py`.

See [`../CLAUDE.md`](../CLAUDE.md) for the full monorepo overview and [`../backend/CLAUDE.md`](../backend/CLAUDE.md) for backend conventions.

## Environment & external surfaces

The plugin will need to interact with three distinct surfaces; each has its own constraints which are still being mapped out.

### 1. The Obsidian plugin runtime

- TypeScript plugin running inside Obsidian (desktop, possibly mobile).
- Standard Obsidian plugin model: `manifest.json` + bundled `main.js` + optional `styles.css`, installed under `<vault>/.obsidian/plugins/<plugin-id>/`.
- API surface includes: `Plugin`, `ItemView`, `WorkspaceLeaf`, `Vault`, `MetadataCache`, `Workspace` events, and DOM access to internal views (file-explorer, editor) — the last is **unofficial** and historically unstable.
- The API is mature but documented as "still subject to change"; pin behaviour to specific Obsidian versions and avoid relying on internals where avoidable.

### 2. The user's vault

- Notes are plain Markdown with YAML frontmatter.
- Folders mirror PARA (Projects / Areas / Resources / Archives) plus an Inbox.
- Frontmatter is the **only** place the plugin or backend may write metadata. Body text is read-only from PipGraph's perspective.
- The vault must remain fully usable with the plugin **disabled** — any decorations, panels, or behaviours must be additive.

### 3. The PipGraph backend

- HTTP service, default `http://localhost:8000`, prefix `/api/v1/dev`.
- All graph state (Episodics, PARA Entities, relationships) lives there.
- Key relevant endpoints today (subject to change, always re-check `backend/app/api/endpoints/dev.py`):
  - `POST /dev/process-note`, `POST /dev/episode` — ingest a note.
  - `GET /dev/episodic/unlinked` — candidates for triage.
  - `POST /dev/make-suggestions` — get suggested PARA targets for a note.
  - `POST /dev/link-entity-episode`, `POST /dev/link-para-nodes` — apply user decisions.

## Working principles for this directory

1. **Research before commitment.** Every non-trivial design choice (panel layout, decoration mechanism, sync model, conflict handling) gets a note in `.docs/suggestions/` *before* it gets code.
2. **Reuse Obsidian.** If Obsidian already does something well (search, folder UI, hotkeys, mobile rendering), don't re-implement it.
3. **The plugin is a client, not a brain.** Logic lives in the backend; the plugin orchestrates, displays, and dispatches user intent.
4. **Non-destructive.** Body of notes is never modified by the plugin. Frontmatter changes are explicit, minimal, and reversible.
5. **Graceful absence.** With the plugin disabled or the backend offline, the vault must remain a normal Obsidian vault.
6. **Iterative.** Ship a minimum useful triage flow first; layer enrichment, automation, and visualisation later.

## Tracking plan progress & decisions

Implementation is organised into modules under [`.docs/plans/`](./.docs/plans). Each module file is the **single source of truth** for its own status and progress; each questionnaire under [`.docs/plans/questions/`](./.docs/plans/questions) is the single source of truth for its own decisions. **Do not create a separate tracker file** — state belongs next to context.

The routine:

- **Starting a module:** flip its `Status:` line in `Mxx-…md` and the matching row in [`00-roadmap.md`](./.docs/plans/00-roadmap.md) status board. Record the branch name in the same edit.
- **Completing a step:** tick the matching `- [ ]` in the module's Deliverables / Step-by-step in the same commit that ships the change. Don't tick speculatively.
- **Deciding a questionnaire item:** append a row to that questionnaire's `## Decisions` table (date, question, answer, reason) in the same PR that *implements* the decision. The discussion above the table stays as history — never delete it.
- **Reality contradicts the plan:** update the module file *before* (or in the same PR as) the code that diverges. Stale plans are worse than no plan.
- **No new tracker files** without discussing first. If a need arises, that's a signal to revisit conventions, not to add a file.

See [`./.docs/plans/README.md`](./.docs/plans/README.md) for the full conventions (status vocabulary, file index, working principles).

### Session orientation — `JOURNAL.md`

A short rolling digest at [`./JOURNAL.md`](./JOURNAL.md) carries **session-level** context: what was worked on recently, what's currently open, links to artefacts. It is **not a tracker** (module-level state still lives in `.docs/plans/`) and it is **not a plan** — it's a 30-second answer to «что было недавно, что висит».

Routine:

- **Session start:** read `Now`, `Open questions`, and the top `Recent sessions` entry. That's the context.
- **Session end:** update `Now` + `Open questions` to current truth, prepend one new entry to `Recent sessions` (≤10 lines, with links to artefacts).
- **Size discipline:** `Recent sessions` ≤ 5 entries. Older work gets compressed to a one-liner in `Archive` or dropped if fully captured by a plan/questionnaire.

`JOURNAL.md` is local-only; do not link to it from code or PRs.

## Where to look next

- [`.docs/suggestions/`](./.docs/suggestions) — open research questions, options under consideration, and recommendations. **Start here when planning any feature.**
- [`.docs/plans/`](./.docs/plans) — modular implementation plan + decision questionnaires. **Start here when implementing.**
- [`../backend/app/api/endpoints/dev.py`](../backend/app/api/endpoints/dev.py) — the live contract for what the plugin can ask the backend to do.
- [`../pipgraph-web/CLAUDE.md`](../pipgraph-web/CLAUDE.md) — sibling client; useful for understanding how the web prototype approaches the same data, but its UI assumptions (a browser tab) do not transfer 1:1.

---

**For Claude Code working in this directory:** Do *not* invent technical decisions that aren't captured here, in `.docs/suggestions/`, or in `.docs/plans/`. If a question isn't answered, surface it — propose options, don't pick one silently. Treat the existence of a `.docs/suggestions/` or `.docs/plans/questions/` note as the authoritative starting point for the topic it covers.
