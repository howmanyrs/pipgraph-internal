# PipGraph Obsidian Plugin — Direction & Environment

> **Status: iterative build, still early.** A working plugin skeleton has shipped into a test vault — settings, a typed backend client, inbox-capture commands, and a vault↔graph folder mirror — while the triage panel at the heart of the design is still taking shape. This file describes *where this component sits*, *what it is for*, and *what surrounds it* — the slow-changing frame. Concrete, churning decisions (APIs, UI patterns, file layouts) live under [`.docs/suggestions/`](./.docs/suggestions) (design) and [`.docs/plans/`](./.docs/plans) (how it ships); *what actually stands week-to-week* lives there and in [`JOURNAL.md`](./JOURNAL.md), not here.

## What this is

`pipgraph-obsidian` is the **Obsidian plugin** in the PipGraph monorepo. It is a thin client over the PipGraph backend (see [`../backend`](../backend)) — analogous in role to [`../pipgraph-web`](../pipgraph-web), but embedded inside the user's Obsidian vault rather than delivered through a browser.

The plugin is built **iteratively**: real code now exists and runs, but expect frequent direction changes, throwaway prototypes, and research-driven course corrections. Treat any module as provisional unless its plan file marks it shipped.

## Why Obsidian, and what role does it play

Obsidian is the user's **native authoring environment** for notes. The plugin does **not** try to replace Obsidian's UI; instead it leans on what Obsidian already does well:

- **File explorer + folders** — the user's PARA structure (Projects / Areas / Resources / Archives) lives as folders. Notes are visible, organisable, and searchable through Obsidian's own widgets.
- **Tags, links, frontmatter** — notes get *enriched* (tags, links to PARA entities, embeddings) but the body of the note stays untouched. The backend already follows a non-destructive policy; the plugin must respect it.
- **Native editor, search, graph, hotkeys, mobile clients** — all of these are reused as-is.

PipGraph's plugin contributes the capabilities Obsidian lacks: chiefly a dedicated panel that helps the user **triage their inbox of unprocessed notes** using LLM-suggested placements — the centre of the design problem — and, around it, keeping the PARA folder structure and the graph in sync. See [What exists today](#what-exists-today-and-where-its-heading) for the current silhouette.

## The core design problem (the hard part)

The user dumps notes into an inbox folder. PipGraph's backend can suggest, for each note, which PARA entity / folder it most likely belongs to (via hybrid search + LLM). The question this plugin must answer is:

> **How does the user efficiently confirm, correct, or reject these suggestions, in a way that feels like GTD inbox processing rather than another database UI?**

There is an additional, more subtle subproblem:

> **The most informative way to show a suggestion is to *place* the note in its proposed folder — so the user sees it in context. But the user must immediately be able to tell which notes landed there by a human decision vs. by an automatic suggestion that still needs confirmation.**

This requires some kind of visual "tentative / pending review" indicator on the file-explorer entry itself. Whether that is feasible — and how — is a research question. See [`.docs/suggestions/`](./.docs/suggestions).

## What exists today, and where it's heading

A deliberately coarse silhouette — the precise, churning detail is in [`.docs/plans/`](./.docs/plans) and [`JOURNAL.md`](./JOURNAL.md), which evolve faster than this file should:

- **Shipped, exercised in a vault:** a typed HTTP client over the backend; a settings tab (backend URL, PARA root folder, inbox/drafts subfolders, and an **LLM provider** section — pick Cloud.ru/OpenRouter + keys/models, pushed to the backend via `/dev/llm-config`, applied on backend restart); inbox-capture commands (quick-capture modal, draft note, process-a-draft); a **folder ↔ entity mirror** — PARA folders under the root are reflected as graph entities, the filesystem hierarchy becomes `BELONGS_TO`, and deleting a folder cascades to its orphaned notes (folders with no summary get a small file-explorer marker); a **tabbed triage panel** whose *Entity Inspector* shows a clicked folder's graph node with an editable summary; and **drag-to-place** — dragging a note from the inbox tab onto a PARA folder moves the file and links it (`MENTIONS`) in one gesture.
- **In flight / next:** the **triage queue** at the heart of the panel — confirm / correct / reject suggested placements (still a skeleton), file-explorer decorations that distinguish *human-placed* from *suggested* notes, and pulling backend state down into the vault. A few backend gaps the plugin has surfaced (e.g. editing an entity's name / path — summary already landed) are catalogued, not yet built.

These lists move constantly — read this as a frame, not a status board. The plan files are the source of truth for what is actually done; this section only orients you.

## Where this plugin sits in the monorepo

```
pipgraph/
├── backend/           # FastAPI service — single source of truth for graph state
├── pipgraph-web/      # Next.js web client (rapid prototyping UI)
└── pipgraph-obsidian/ # ← this plugin (in-vault UI for triage + enrichment)
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

- HTTP service under the prefix `/api/v1/dev`; the plugin's settings point at it (local by default). The canonical port, the full endpoint table, and the data model live in [`../backend/CLAUDE.md`](../backend/CLAUDE.md) — not duplicated here.
- All graph state (Episodics, PARA entities, relationships) lives there; the plugin never touches Neo4j or an LLM directly.
- For the plugin's *own* view — which endpoints it already wraps, and the gaps it still needs — see [`.docs/overview/api-surface.md`](./.docs/overview/api-surface.md) and [`.docs/overview/future-methods.md`](./.docs/overview/future-methods.md). The authoritative contract is always [`dev.py`](../backend/app/api/endpoints/dev.py) / the live OpenAPI.

## Working principles for this directory

1. **Research before commitment.** Every non-trivial design choice (panel layout, decoration mechanism, sync model, conflict handling) gets a note in `.docs/suggestions/` *before* it gets code.
2. **Reuse Obsidian.** If Obsidian already does something well (search, folder UI, hotkeys, mobile rendering), don't re-implement it.
3. **The plugin is a client, not a brain.** Logic lives in the backend; the plugin orchestrates, displays, and dispatches user intent.
4. **Non-destructive.** Body of notes is never modified by the plugin. Frontmatter changes are explicit, minimal, and reversible.
5. **Graceful absence.** With the plugin disabled or the backend offline, the vault must remain a normal Obsidian vault.
6. **Iterative.** Ship a minimum useful triage flow first; layer enrichment, automation, and visualisation later.

## Tracking plan progress & decisions

Implementation is organised into modules under [`.docs/plans/`](./.docs/plans). Each module file is the **single source of truth** for its own status and progress; each questionnaire under [`.docs/plans/questions/`](./.docs/plans/questions) is the single source of truth for its own decisions. **Do not create a separate tracker file** — state belongs next to context.

### The plan describes the present, not its own history

Keep the plan **maximally fresh**: a reader should learn *what is true now*, never have to reconstruct what the plan used to say.

- **Module files (`Mxx-…md`), [`00-roadmap.md`](./.docs/plans/00-roadmap.md), and `overview/` snapshots hold current truth only.** When reality changes, rewrite the affected text *in place* — no revision banners, no «раньше X, теперь Y», no superseded descriptions left lying around. Outdated or no-longer-relevant decisions are *removed*, not annotated.
- **One exception: the `## Decisions` tables in questionnaires.** They are the deliberate, append-only record of *why* a choice was made — that rationale stays even when the surrounding prose is trimmed.
- **Research clusters (`to-research/`, …) may carry the messiness of iteration while live.** Once a cluster's conclusion is promoted into a module, the cluster moves to [`archive/`](./.docs/plans/archive) and stops influencing anything — neither through stale forks/deviations explored during the research, nor by being cited from a live module. Deviations tried out while researching must not leak back into the plan after archival.

The same discipline applies to [`JOURNAL.md`](./JOURNAL.md): it carries only *live* context — resolved questions and superseded sessions are dropped or compressed, not kept around struck-through.

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
- **Size discipline:** `Recent sessions` ≤ 10 entries. Older work gets compressed to a one-liner in `Archive` or dropped if fully captured by a plan/questionnaire.

`JOURNAL.md` is local-only; do not link to it from code or PRs.

## Source map & local build

Where things live in the code (entry points, not an exhaustive index — modules churn; treat this as orientation):

```
src/
├── main.ts                       # Plugin entry — onload/onunload, ribbon, view registration, wiring
├── commands/register.ts          # Every command-palette command (incl. the not-yet-implemented stubs)
├── modals/NewInboxNoteModal.ts   # Capture modal behind "New inbox note"
├── settings/                     # Settings tab, settings model + path helpers, folder autosuggest
├── backend/                      # Typed HTTP client over the backend (PipGraphClient, transport, errors, types)
├── folder-mirror/                # Folder ↔ entity mirror (FolderMirror) + explorer decoration (folder summary, file processing/failed markers)
├── drag/                         # Drag-to-place (DragToPlace) — inbox note → PARA folder = move + MENTIONS
├── vault/                        # Path helpers shared by capture + drag (resolveUniqueFilePath)
├── frontmatter/                  # Read-only pipgraph.uuid reader (uuid-primary resolve, not yet active)
└── views/TriagePanelView.ts      # Right-sidebar triage panel (tabbed: Inbox + Entity Inspector; triage queue still a stub)
manifest.json                     # Obsidian plugin metadata (id `pipgraph`, desktop-only)
esbuild.config.mjs                # Build pipeline (dev watch / prod minify)
styles.css                        # Panel / modal / decoration styling
```

Local build & deploy:

- `npm install`, then `npm run dev` (esbuild watches `src/` → `main.js`) or `npm run build` (minified bundle).
- Deploy into a test vault with [`deploy-to-vault.sh`](./deploy-to-vault.sh), or symlink this directory into `<vault>/.obsidian/plugins/pipgraph`.
- Reload Obsidian (`Ctrl+R` / `Cmd+R`) after each rebuild to pick up the new bundle.

## Where to look next

- [`.docs/suggestions/`](./.docs/suggestions) — open research questions, options under consideration, and recommendations. **Start here when planning any feature.**
- [`.docs/plans/`](./.docs/plans) — modular implementation plan + decision questionnaires. **Start here when implementing.**
- [`../backend/app/api/endpoints/dev.py`](../backend/app/api/endpoints/dev.py) — the live contract for what the plugin can ask the backend to do.
- [`../pipgraph-web/CLAUDE.md`](../pipgraph-web/CLAUDE.md) — sibling client; useful for understanding how the web prototype approaches the same data, but its UI assumptions (a browser tab) do not transfer 1:1.

---

**For Claude Code working in this directory:** Do *not* invent technical decisions that aren't captured here, in `.docs/suggestions/`, or in `.docs/plans/`. If a question isn't answered, surface it — propose options, don't pick one silently. Treat the existence of a `.docs/suggestions/` or `.docs/plans/questions/` note as the authoritative starting point for the topic it covers.
