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
  initialized: boolean;
}

export const DEFAULT_SETTINGS: PipGraphSettings = {
  backendUrl: "http://localhost:8001",
  apiKey: "",
  rootFolder: "PipGraph",
  inboxRelativePath: "Inbox",
  draftsRelativePath: "drafts",
  autoMirrorFolders: false,
  focusSuggest: false,
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
