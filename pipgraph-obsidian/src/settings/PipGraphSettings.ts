export interface PipGraphSettings {
  backendUrl: string;
  apiKey: string;
  rootFolder: string;
  inboxRelativePath: string;
  draftsRelativePath: string;
  initialized: boolean;
}

export const DEFAULT_SETTINGS: PipGraphSettings = {
  backendUrl: "http://localhost:8000",
  apiKey: "",
  rootFolder: "PipGraph",
  inboxRelativePath: "Inbox",
  draftsRelativePath: "drafts",
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
