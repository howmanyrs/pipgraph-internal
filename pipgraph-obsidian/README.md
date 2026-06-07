# PipGraph — Obsidian plugin

In-vault UI for the PipGraph triage flow. This is the Obsidian client; the backend (FastAPI + Neo4j) lives in [`../backend`](../backend) and is the source of truth for all graph state. The plugin never talks to Neo4j or an LLM directly — it only calls the backend's HTTP API, and it never rewrites the body of your notes.

> ⚠️ **This guide is a moving target.** The plugin is built iteratively. Some commands are still placeholders that only show a "not implemented yet" notice, and a few flows below are brand new. Treat this README as a snapshot of what works today, plus a heads-up on [what's coming](#coming-soon).

## What it does, in plain terms

PipGraph turns your vault into a triage pipeline on the **PARA** model (Projects / Areas / Resources / Archives). You dump notes into an **Inbox** folder; the backend reads them and extracts the entities (topics, people, projects, tools) each note is really about. The plugin then lets you:

- **capture** notes quickly into the Inbox,
- **see suggested PARA folders** for a note, ranked by how well it matches, and **confirm a placement** in one gesture,
- **inspect** the graph entity behind any PARA folder (and edit its summary),
- keep your **PARA folder structure in sync** with the graph.

It does *not* replace Obsidian's editor, search, or file explorer — it adds only the bridge to the backend and the triage workflow on top of your folders.

### Where it shows up in Obsidian

| Surface | Where | What it's for |
|---|---|---|
| **Ribbon icon** (inbox) | Left ribbon | Opens the triage panel. |
| **Triage panel** | Right sidebar | Tabbed: **Inbox** (notes waiting in your inbox) + **Entity Inspector** (the graph node behind a clicked folder). A **Focus suggest** toggle sits above the tabs. |
| **Command palette** | `Ctrl/Cmd+P` → "PipGraph" | All commands (see the [reference](#command-reference)). |
| **Settings tab** | Settings → Community plugins → PipGraph | Backend URL, root/inbox/drafts folders, auto-mirror, **LLM provider**, **Prompts**, **Danger zone**. |
| **File-explorer markers** | On folders & notes | `⟳` processing · `⚠` failed · `❗` auto-named (needs a real name) · a dot on folders whose entity has no summary yet · `NN%` match badges in Focus-suggest mode. |
| **Right-click menus** | Folders & notes | Folder → "Sync folder to backend"; failed note → "Process note"; auto-named note → "Regenerate name with LLM"; candidate folder → "Confirm placement here". |

## First-time setup

1. Start the backend (see [`../backend`](../backend)). By default the plugin expects it at **`http://localhost:8001`**.
2. Open **Settings → Community plugins → PipGraph** and set your **Root folder** (default `PipGraph`). If it doesn't exist, the tab offers a **Create folder** button.
3. *(Optional)* In the **LLM provider** section pick your provider, key, and models — see below.

The Inbox (`PipGraph/Inbox`) and drafts (`PipGraph/Inbox/drafts`) subfolders are created on demand the first time you capture a note.

### Settings reference

| Setting | Default | Meaning |
|---|---|---|
| Backend URL | `http://localhost:8001` | Base URL of the PipGraph backend. Changing it rebuilds the client immediately. |
| API key | *(empty)* | Reserved for future auth. Stored unencrypted in `data.json`. |
| Root folder | `PipGraph` | The vault folder where PipGraph manages your PARA structure. |
| Inbox folder name | `Inbox` | Subfolder under root where captured notes land. |
| Drafts subfolder name | `drafts` | Subfolder inside Inbox for raw drafts you write before processing. |
| Auto-mirror folders to backend | off | When on, folders under root (except Inbox and freshly-made "Untitled" folders) mirror to PARA entities automatically on create/rename/load. When off, you mirror them explicitly by right-clicking. |

Three richer sections live below the basic settings:

- **LLM provider** — choose the backend's provider (Cloud.ru / OpenRouter), API key, and model names. The backend is the source of truth, so this loads live from it; **changes apply on the backend's next restart**.
- **Prompts** (*Промпты*) — edit the domain guidance injected into the entity-extraction prompts (e.g. how summaries are written, what counts as a tag-worthy entity). Edits **apply live on the backend — no restart needed** — and each card has a **Reset to default**.
- **Danger zone** — two confirmed debug resets: **Wipe graph** (deletes every node + edge on the backend; leaves your files alone) and **Clear vault folder** (deletes notes + emptied PARA subfolders under the root + pending capture files; leaves the graph alone).

## Capturing notes

**PipGraph: New inbox note** — opens a capture modal. Type or paste, then **Add** (`Ctrl/Cmd+Enter`). The backend ingests the text, **auto-names** it, and the plugin writes the file into your Inbox and opens it. The backend is the source of truth: if the call fails nothing is written, so you never get an orphaned note. If auto-naming itself fails, the note still lands with a fallback name and an `❗` marker — right-click → **Regenerate name with LLM** to try again.

**PipGraph: New draft inbox note** — creates an empty `Draft-<timestamp>.md` in the drafts subfolder for composing a longer note locally. Nothing is sent yet.

**PipGraph: Process current draft** — visible only when the active file is a draft. Sends its content to the backend and **moves** the file up into the Inbox. Empty drafts are rejected; a name clash asks you to rename first.

## Placing notes into PARA

Two ways to move an inbox note into the folder it belongs to — both **move the file and link it** (`MENTIONS`) in one step, and kick off background processing:

- **Drag-to-place** — drag a note from the panel's **Inbox** tab onto any PARA folder.
- **Focus suggest** — flip the **Focus suggest** toggle above the panel tabs to get folder recommendations for the currently selected note (the note open in your editor, or your last Inbox selection):
  - **toggle off** → your real folders get **`NN%` match badges** in the file explorer; right-click a suggested folder → **"Confirm placement here"**.
  - **toggle on** → the real tree under the root is replaced by a **"ghost tree"** of candidate folders ranked by match %. Click to preview, right-click to confirm, or drag a note straight onto a ghost folder. Close the panel and the real tree returns.

## Inspecting & editing entities

Click any PARA folder in the file explorer and open the **Entity Inspector** tab: it shows that folder's graph node — name, type, path, created date, an **editable summary** (with **Save**), and recently linked notes. Clicking a folder updates the tab *without* stealing focus, so you stay where you are.

## Status markers & re-processing

The file explorer reflects backend state on each note:

- **`⟳`** — the note is being processed (entity extraction) right now.
- **`⚠`** — processing failed. Right-click → **Process note** to retry just that one, or run **PipGraph: Process all failed notes** to retry every failed note at once.
- **`❗`** — the note got an auto-generated fallback name because LLM naming failed. Right-click → **Regenerate name with LLM**.

In the panel's **Inbox** tab, a capture still in flight shows `⟳`, and one that failed to reach the backend shows `⚠` with retry / save-to-drafts / discard options. Markers survive an Obsidian restart and re-sync from the backend.

## Folder ↔ entity mirror

Your PARA structure lives as ordinary folders under the root; the plugin mirrors it into the graph so the filesystem stays the source of truth:

- **Create / sync** — a managed folder (under root, outside the Inbox subtree) becomes a `(:Entity:Area)` bound to its path, and its place in the tree becomes the `BELONGS_TO` hierarchy. With auto-mirror **off** (default), do this via **right-click → "PipGraph: Sync folder to backend"**; with it **on**, create/rename/load mirror automatically (except unnamed "Untitled" folders).
- **Delete** — deleting a folder cascades on the backend: its entity and any notes that *only* belonged to it are removed.
- **Empty-summary marker** — a folder whose entity has no summary yet is marked, so you can see which PARA containers still need meaning.

## Command reference

All under the **PipGraph:** prefix in the command palette (`Ctrl/Cmd+P`).

| Command | What it does |
|---|---|
| **Open triage panel** | Open/reveal the right-sidebar panel (same as the ribbon icon). |
| **New inbox note** | Capture modal → named note in the Inbox. |
| **New draft inbox note** | Empty local draft to compose first. |
| **Process current draft** | Send the active draft to the backend, move it into the Inbox. *(Only when a draft is active.)* |
| **Refresh triage queue** | Re-render the open triage panels. |
| **Process all failed notes** | Retry every note in the failed-processing set. *(Only when there are failed notes.)* |
| **Sync from backend** | *Placeholder — coming in M4.* |
| **Auto-process inbox** | *Placeholder — coming next (see below).* |

Right-click items (context menus, not palette commands): **Process note** (on a `⚠` note), **Regenerate name with LLM** (on an `❗` note), **Confirm placement here** (on a candidate folder), **Sync folder to backend** (on a managed folder).

## Coming soon

In active development — described here so you know where this is heading:

- **Frontmatter enrichment** — based on the entity tags the backend extracts from a note, the plugin will write those tags/links into the note's **YAML frontmatter** (the body stays untouched), so your graph knowledge surfaces as native Obsidian tags and links.
- **Automatic placement on capture** — new notes auto-assigned to their best-matching PARA folder as you add them. The mechanism still needs tuning; the **manual mode already works today** — that's the Focus-suggest recommendations above.
- **Reporting dashboard** — using the graph's entity↔note relationships and timestamps to build a status dashboard: currently active topics, reminders about abandoned/stale ones, and useful rolled-up summaries of where your notes stand.

---

*Building or contributing to the plugin?* Setup, source layout, and design direction live in [`CLAUDE.md`](./CLAUDE.md) and [`.docs/plans/`](./.docs/plans) — this README is for using the plugin, not developing it.
