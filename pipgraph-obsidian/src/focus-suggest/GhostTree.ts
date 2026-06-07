import { Menu, setIcon } from "obsidian";
import type { TFile } from "obsidian";
import type { ParaEntity } from "../backend";
import { PIPGRAPH_DRAG_MIME } from "../drag/DragToPlace";
import type { FolderScores } from "./SuggestionEngine";

/**
 * Ghost-tree renderer (M5b Phase 2). Builds a single DOM subtree of phantom PARA
 * folders from {@link FolderScores}, each carrying its match %. "Ghost" = DOM
 * only — Obsidian's indexes (search / graph / quick-switcher) never see it; the
 * file truth is untouched. Differentiated from real rows by opacity + a dotted
 * host border and our own `pipgraph-ghost-*` classes (no icon/emoji — decision
 * 2026-06-07), so themes and other file-tree plugins can't mistake it for a
 * real `nav-folder`/`nav-file`.
 */

export interface GhostNode {
  name: string;
  /** Vault folder path mirroring this PARA entity. */
  path: string;
  /** The PARA entity, when this folder is mirrored (intermediate gaps have none). */
  entity?: ParaEntity;
  /** Match score 0..1, when the backend ranked this folder. */
  score?: number;
  children: GhostNode[];
}

export interface GhostTreeCallbacks {
  /** Left-click / "Open note": open the target note to read before deciding. */
  onOpenNote: () => void;
  /** "Confirm placement here": place the target note into this folder-entity. */
  onConfirm: (node: GhostNode) => void;
  /** "Skip": drop the current note's suggestions (keep the tree visible). */
  onSkip: () => void;
  /** An Inbox note was dragged & dropped onto this folder (move+link). */
  onDropNote: (node: GhostNode, sourcePath: string) => void;
}

export interface GhostTreeOptions {
  /** True while a make-suggestions call is in flight (shows a loading hint). */
  loading?: boolean;
  /**
   * Vault paths of notes whose heavy processing job is in flight. Each is shown
   * as a row inside its (ghost) folder with a spinning circular-arrow icon —
   * the "I just placed this here, it's being processed" cue. Driven by the
   * {@link ProcessingTracker}; the row disappears when the job settles.
   */
  processingPaths?: Set<string>;
}

// A branch is drawn expanded if it (or any descendant) scores at least this.
const EXPAND_THRESHOLD = 0.1;

export function buildGhostTree(
  rootFolder: string,
  scores: FolderScores,
  target: TFile | null,
  callbacks: GhostTreeCallbacks,
  options: GhostTreeOptions = {},
): HTMLElement {
  const root = rootFolder.replace(/\/+$/, "");
  const nodes = buildNodes(root, scores);

  const container = createDiv({ cls: "pipgraph-ghost-tree" });
  container.createDiv({
    cls: "pipgraph-ghost-separator",
    text: options.loading ? "focus suggest · scoring…" : "focus suggest",
  });

  if (nodes.length === 0) {
    container.createDiv({
      cls: "pipgraph-ghost-empty",
      text: "No PARA folders under your root yet.",
    });
    return container;
  }

  const processing = options.processingPaths ?? new Set<string>();
  for (const node of nodes) {
    renderNode(container, node, 0, target, callbacks, processing);
  }
  return container;
}

/** Build the folder forest under `root` from the entity list (by `file_path`). */
function buildNodes(root: string, scores: FolderScores): GhostNode[] {
  const prefix = `${root}/`;
  const byPath = new Map<string, GhostNode>();
  const roots: GhostNode[] = [];

  const ensure = (path: string): GhostNode => {
    const existing = byPath.get(path);
    if (existing) return existing;
    const node: GhostNode = {
      name: path.slice(path.lastIndexOf("/") + 1),
      path,
      children: [],
    };
    byPath.set(path, node);
    const parentPath = path.slice(0, path.lastIndexOf("/"));
    if (parentPath === root) {
      roots.push(node);
    } else {
      ensure(parentPath).children.push(node);
    }
    return node;
  };

  // Sort by path so parents materialise before children deterministically.
  const entities = scores.entities
    .filter((e) => e.file_path && e.file_path.startsWith(prefix))
    .sort((a, b) => (a.file_path! < b.file_path! ? -1 : 1));

  for (const entity of entities) {
    const node = ensure(entity.file_path!);
    node.entity = entity;
    node.score = scores.scoreByUuid.get(entity.uuid);
  }

  sortTree(roots);
  return roots;
}

/** Highest score in a subtree (drives default expansion). */
function maxScore(node: GhostNode): number {
  let m = node.score ?? 0;
  for (const child of node.children) m = Math.max(m, maxScore(child));
  return m;
}

/** Sort each level by score (desc), then name. */
function sortTree(nodes: GhostNode[]): void {
  nodes.sort(
    (a, b) =>
      (b.score ?? -1) - (a.score ?? -1) || a.name.localeCompare(b.name),
  );
  for (const n of nodes) sortTree(n.children);
}

function renderNode(
  parent: HTMLElement,
  node: GhostNode,
  depth: number,
  target: TFile | null,
  cb: GhostTreeCallbacks,
  processing: Set<string>,
): void {
  const row = parent.createDiv({ cls: "pipgraph-ghost-folder" });
  row.style.setProperty("--pipgraph-ghost-depth", String(depth));

  // Notes currently processing whose folder is exactly this one (just placed
  // here). They render as child rows with a spinning icon, so the folder is
  // forced open to make the fresh placement visible.
  const processingHere = [...processing].filter(
    (p) => p.slice(0, p.lastIndexOf("/")) === node.path,
  );
  const hasChildren = node.children.length > 0 || processingHere.length > 0;
  const expanded =
    processingHere.length > 0 || maxScore(node) >= EXPAND_THRESHOLD;

  const twistie = row.createSpan({ cls: "pipgraph-ghost-twistie" });
  if (hasChildren) setIcon(twistie, expanded ? "chevron-down" : "chevron-right");

  row.createSpan({ cls: "pipgraph-ghost-name", text: node.name });

  const pct = node.score != null ? Math.round(node.score * 100) : null;
  const badge = row.createSpan({ cls: "pipgraph-ghost-score" });
  if (pct != null) {
    badge.setText(`${pct}%`);
    badge.addClass(scoreClass(node.score!));
  } else {
    badge.setText("—");
    badge.addClass("pipgraph-ghost-score--none");
  }

  const noteLabel = target?.basename ?? "this note";
  row.setAttr(
    "aria-label",
    pct != null
      ? `${noteLabel} → ${node.name} (score: ${pct}%)`
      : `${noteLabel} → ${node.name}`,
  );

  // Left-click on the row (not the twistie) opens the target note.
  row.addEventListener("click", (ev) => {
    ev.preventDefault();
    ev.stopPropagation();
    cb.onOpenNote();
  });

  // Right-click: context menu (idiomatic, no accidental file move).
  row.addEventListener("contextmenu", (ev) => {
    ev.preventDefault();
    ev.stopPropagation();
    const menu = new Menu();
    if (node.entity) {
      menu.addItem((item) =>
        item
          .setTitle("Confirm placement here")
          .setIcon("check")
          .onClick(() => cb.onConfirm(node)),
      );
    }
    menu.addItem((item) =>
      item
        .setTitle("Open note")
        .setIcon("file")
        .onClick(() => cb.onOpenNote()),
    );
    menu.addItem((item) =>
      item.setTitle("Skip").setIcon("skip-forward").onClick(() => cb.onSkip()),
    );
    menu.showAtMouseEvent(ev);
  });

  // Drag-to-place: drop an Inbox note (from the panel's Inbox tab) onto a
  // candidate folder = move+link, the same gesture as the real-tree drag.
  // Only folders backed by an entity are valid targets.
  if (node.entity) {
    row.addEventListener("dragover", (ev) => {
      if (!ev.dataTransfer?.types.includes(PIPGRAPH_DRAG_MIME)) return;
      ev.preventDefault();
      ev.stopPropagation();
      ev.dataTransfer.dropEffect = "move";
      row.addClass("pipgraph-ghost-drop-target");
    });
    row.addEventListener("dragleave", () =>
      row.removeClass("pipgraph-ghost-drop-target"),
    );
    row.addEventListener("drop", (ev) => {
      row.removeClass("pipgraph-ghost-drop-target");
      const source = ev.dataTransfer?.getData(PIPGRAPH_DRAG_MIME);
      if (!source) return;
      ev.preventDefault();
      ev.stopPropagation();
      cb.onDropNote(node, source);
    });
  }

  if (hasChildren) {
    const childrenEl = parent.createDiv({ cls: "pipgraph-ghost-children" });
    if (!expanded) childrenEl.addClass("is-collapsed");
    for (const child of node.children) {
      renderNode(childrenEl, child, depth + 1, target, cb, processing);
    }
    // Sub-folders first (explorer convention), then the in-flight notes.
    for (const path of processingHere) {
      renderProcessingNote(childrenEl, path, depth + 1);
    }
    twistie.addEventListener("click", (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      const collapsed = !childrenEl.hasClass("is-collapsed");
      childrenEl.toggleClass("is-collapsed", collapsed);
      setIcon(twistie, collapsed ? "chevron-right" : "chevron-down");
    });
  }
}

/**
 * A note placed into this folder whose processing job is in flight. Non-
 * interactive: the note name followed by the same `⟳` glyph the real-tree
 * file-marker uses (styles.css `.pipgraph-processing`), signalling "this just
 * landed here and is being processed". Disappears on the next re-render once the
 * {@link ProcessingTracker} drops its path (settled).
 */
function renderProcessingNote(
  parent: HTMLElement,
  path: string,
  depth: number,
): void {
  const name = path.slice(path.lastIndexOf("/") + 1).replace(/\.md$/, "");
  const row = parent.createDiv({ cls: "pipgraph-ghost-note" });
  row.style.setProperty("--pipgraph-ghost-depth", String(depth));
  // Empty twistie-width spacer so the name lines up under the folder name.
  row.createSpan({ cls: "pipgraph-ghost-twistie" });
  row.createSpan({ cls: "pipgraph-ghost-note-name", text: name });
  // Reuse the real-tree processing glyph (⟳, accent, not animated).
  row.createSpan({ cls: "pipgraph-ghost-note-status", text: "⟳" });
  row.setAttr("aria-label", `${name} — processing…`);
}

function scoreClass(score: number): string {
  if (score >= 0.7) return "pipgraph-ghost-score--high";
  if (score >= 0.4) return "pipgraph-ghost-score--mid";
  return "pipgraph-ghost-score--low";
}
