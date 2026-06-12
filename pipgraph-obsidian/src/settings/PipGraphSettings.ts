import type { InboxSort } from "../views/inbox/InboxSemantic";

export interface PipGraphSettings {
  backendUrl: string;
  apiKey: string;
  rootFolder: string;
  inboxRelativePath: string;
  draftsRelativePath: string;
  // When true, every managed folder under root is auto-mirrored to a PARA
  // entity (on create, rename, and plugin load). When false, mirroring is
  // explicit only (right-click → "Sync folder to backend"). Freshly-created
  // "Untitled" folders are never auto-mirrored regardless of this flag.
  autoMirrorFolders: boolean;
  // Panel-global "Focus suggest" toggle (M5b): when on AND a triage panel is
  // open, the real PARA subtree under root is hidden and a ghost-tree of folder
  // candidates (with match %) is drawn in its place. Persisted across sessions;
  // closing the panel deactivates the mode without flipping this flag.
  focusSuggest: boolean;
  // Row order inside the "Focus suggest" ghost-tree (M5b). "score" (default) =
  // ranked by match % descending (the original behaviour); "alpha" = A–Z, like
  // the real file-explorer folders. Switchable from the ghost-block header;
  // persisted across sessions.
  focusSuggestSort: "score" | "alpha";
  // Inbox-tab "Highlight similar" toggle (A, inbox-tuning 01): dim-highlight
  // notes similar to the selected one. With a no-op similarity provider this is
  // inert; it gates toggle B. Persisted across sessions.
  inboxHighlightSimilar: boolean;
  // Inbox-tab "Auto-select similar" toggle (B): auto-check the highlighted
  // notes into the batch on selection change. Requires A (nothing to select if
  // nothing is highlighted). Persisted across sessions.
  inboxAutoSelectSimilar: boolean;
  // Inbox-tab sort order (inbox-tuning 01). "date" (default) = by `ctime`
  // descending, grouped by day; "semantic" = a future order from pre-extracted
  // frontmatter (plan 02) — inert/disabled until a semantic provider has data.
  // Persisted across sessions.
  inboxSort: InboxSort;
  initialized: boolean;
}

export const DEFAULT_SETTINGS: PipGraphSettings = {
  backendUrl: "http://localhost:8001",
  apiKey: "",
  rootFolder: "PipGraph",
  // "00_" prefix keeps the inbox sorted to the very top of the file explorer
  // (and the ghost tree) — the inbox is the entry point of triage.
  inboxRelativePath: "00_Inbox",
  draftsRelativePath: "drafts",
  autoMirrorFolders: false,
  focusSuggest: false,
  focusSuggestSort: "score",
  inboxHighlightSimilar: false,
  inboxAutoSelectSimilar: false,
  inboxSort: "date",
  initialized: false,
};

const USER_FACING_KEYS = [
  "backendUrl",
  "apiKey",
  "rootFolder",
  "inboxRelativePath",
  "draftsRelativePath",
] as const;

export function hasNonDefaultValues(settings: PipGraphSettings): boolean {
  return USER_FACING_KEYS.some((key) => settings[key] !== DEFAULT_SETTINGS[key]);
}

export function getInboxPath(settings: PipGraphSettings): string {
  const root = settings.rootFolder.replace(/\/+$/, "");
  const inbox = settings.inboxRelativePath.replace(/^\/+|\/+$/g, "");
  return `${root}/${inbox}`;
}

export function getDraftsPath(settings: PipGraphSettings): string {
  const drafts = settings.draftsRelativePath.replace(/^\/+|\/+$/g, "");
  return `${getInboxPath(settings)}/${drafts}`;
}

/**
 * A folder is "managed" (mirrored to a PARA Entity) when it lives under the
 * root folder, is not the root itself, and is not the Inbox subtree.
 * The Inbox (and everything below it, e.g. drafts) is excluded — those notes
 * are unprocessed and must not spawn PARA containers.
 */
export function isManagedFolderPath(
  settings: PipGraphSettings,
  path: string,
): boolean {
  const root = settings.rootFolder.replace(/\/+$/, "");
  if (path === root) return false;
  if (!path.startsWith(`${root}/`)) return false;

  const inbox = getInboxPath(settings);
  if (path === inbox || path.startsWith(`${inbox}/`)) return false;

  return true;
}
