# PipGraph — Obsidian plugin

In-vault UI for the PipGraph triage flow. This is the Obsidian client; the backend (FastAPI + Neo4j) lives in [`../backend`](../backend) and is the source of truth for all graph state. The plugin never talks to Neo4j or an LLM directly — it only calls the backend's HTTP API.

> ⚠️ **This guide is a moving target.** The plugin is built iteratively and still early — commands, panels, and behaviour change often. Some commands below are deliberate placeholders that only show a "not implemented yet" notice. Treat this README as a snapshot, not a contract; when in doubt, the live truth is the code and [`CLAUDE.md`](./CLAUDE.md) / [`.docs/plans/`](./.docs/plans).

## What the plugin does, in plain terms

PipGraph turns your Obsidian vault into a triage pipeline on the PARA model (Projects / Areas / Resources / Archives). You dump notes into an **Inbox** folder; the backend reads them, extracts entities, and (eventually) suggests where each note belongs. The plugin's job is to let you **capture notes**, **keep your PARA folder structure in sync with the graph**, and — once it ships — **confirm or correct those suggestions** without ever rewriting the body of your notes.

It deliberately does *not* replace Obsidian's editor, search, or file explorer. It adds only what Obsidian lacks: a bridge to the PipGraph backend and a triage workflow on top of your existing folders.

### Where it shows up in the Obsidian UI

| Surface | Where | What it's for |
|---|---|---|
| **Ribbon icon** (inbox) | Left ribbon | Opens the triage panel. |
| **Triage panel** | Right sidebar | The future home of inbox triage. Today it shows a first-run "configure root folder" banner, or an "Inbox is empty" placeholder once configured. |
| **Command palette** | `Ctrl/Cmd+P` → type "PipGraph" | All commands (see the manual below). |
| **Settings tab** | Settings → Community plugins → PipGraph | Backend URL, root folder, inbox/drafts names, auto-mirror toggle. |
| **Folder right-click menu** | File explorer, on a managed folder | "PipGraph: Sync folder to backend" — mirror that folder to a PARA entity. |
| **Folder marker** | File explorer | A subtle marker on PARA folders whose graph entity has no summary yet ("describes nothing"). |

> 📹 *GIF suggestion:* a 10-second clip panning over the ribbon icon, the right-sidebar panel, and the settings tab so a new user can locate everything at a glance.

## First-time setup

1. Start the backend (see [`../backend`](../backend)). By default the plugin expects it at **`http://localhost:8001`**.
2. Open **Settings → Community plugins → PipGraph** and set your **Root folder** (default `PipGraph`). If the folder doesn't exist, the settings tab offers a **Create folder** button.
3. That's it — the Inbox (`PipGraph/Inbox`) and drafts (`PipGraph/Inbox/drafts`) subfolders are created on demand the first time you capture a note.

**Settings reference**

| Setting | Default | Meaning |
|---|---|---|
| Backend URL | `http://localhost:8001` | Base URL of the PipGraph backend. Changing it rebuilds the client immediately. |
| API key | *(empty)* | Reserved for future auth. Stored unencrypted in `data.json`. |
| Root folder | `PipGraph` | The vault folder where PipGraph manages your PARA structure. |
| Inbox folder name | `Inbox` | Subfolder under root where captured notes land. |
| Drafts subfolder name | `drafts` | Subfolder inside Inbox for raw drafts you write before processing. |
| Auto-mirror folders to backend | off | When on, every folder under root (except Inbox and freshly-created "Untitled" folders) is mirrored to a PARA entity automatically on create/rename/load. When off, you mirror folders explicitly via right-click. |

> 📹 *GIF suggestion:* the first-run flow — opening settings, picking the root folder, clicking "Create folder", and the panel switching from the banner to the empty-inbox state.

## Command manual (Ctrl/Cmd + P)

All commands are listed under the **PipGraph:** prefix in the command palette.

### Working today

**PipGraph: Open triage panel**
Opens (or reveals) the triage panel in the right sidebar. Same as clicking the ribbon icon. Until you've set a root folder it shows a first-run banner with a link straight to settings.

**PipGraph: New inbox note**
Opens a capture modal. Type or paste your note and hit **Add** (or `Ctrl/Cmd+Enter`). The backend ingests the text, **auto-names** it, and the plugin then creates the file under your Inbox folder with that name and opens it. The backend is the source of truth: if the call fails, nothing is written to disk, so you never get an orphaned note. This is the fastest path for "I have a thought, capture it now."

> 📹 *GIF suggestion:* invoking the command, pasting a paragraph, pressing `Ctrl+Enter`, and the named note appearing in the Inbox.

**PipGraph: New draft inbox note**
Creates an empty `Draft-<timestamp>.md` in the drafts subfolder and opens it for editing. Use this when you want to compose a longer note *before* sending it to the backend. Nothing is sent yet — it's just a local scratch file.

**PipGraph: Process current draft**
Only available (visible/enabled) when the active file is a draft inside the drafts subfolder. It sends the draft's content to the backend as an Episodic, then **moves** the file out of drafts and into the Inbox. Empty drafts are rejected; if a file of the same name already exists in the Inbox, it asks you to rename first.

> 📹 *GIF suggestion:* writing in a draft, running "Process current draft", and the file moving from `drafts/` up into the Inbox.

### Not implemented yet (placeholders)

These commands exist in the palette but currently only show a notice telling you which milestone will deliver them. They're listed here so the palette doesn't surprise you:

| Command | Status |
|---|---|
| **PipGraph: Refresh triage queue** | Coming in M6. |
| **PipGraph: Sync from backend** | Coming in M4. |
| **PipGraph: Auto-process inbox** | Coming in M8 (Phase 1). |

## Folder ↔ entity mirror

Your PARA structure lives as ordinary folders under the root. The plugin mirrors that structure into the graph so the filesystem stays the source of truth:

- **Create / sync** — a managed folder (anything under root except the Inbox subtree) becomes a `(:Entity:Area)` bound to its `file_path`. Its place in the folder tree becomes the `BELONGS_TO` hierarchy. With **auto-mirror off** (the default), do this explicitly via **right-click → "PipGraph: Sync folder to backend"**. With it on, creation/rename/load mirror automatically — except freshly-made "Untitled" folders, which wait for you to give them a real name.
- **Delete** — deleting a folder in Obsidian cascades on the backend: its entity and any notes that *only* belonged to it are removed.
- **Empty-summary marker** — a folder whose entity has no summary yet is marked in the file explorer, so you can see which PARA containers still need meaning.

> 📹 *GIF suggestion:* right-clicking a folder → "Sync folder to backend", followed by the empty-summary marker appearing on it.

---

*Building or contributing to the plugin?* Setup, source layout, and design direction live in [`CLAUDE.md`](./CLAUDE.md) and [`.docs/plans/`](./.docs/plans) — this README is for using the plugin, not developing it.
