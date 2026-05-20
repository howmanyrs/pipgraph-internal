export interface PipGraphSettings {
  backendUrl: string;
  apiKey: string;
  rootFolder: string;
  initialized: boolean;
}

export const DEFAULT_SETTINGS: PipGraphSettings = {
  backendUrl: "http://localhost:8000",
  apiKey: "",
  rootFolder: "PipGraph",
  initialized: false,
};

const USER_FACING_KEYS = ["backendUrl", "apiKey", "rootFolder"] as const;

export function hasNonDefaultValues(settings: PipGraphSettings): boolean {
  return USER_FACING_KEYS.some((key) => settings[key] !== DEFAULT_SETTINGS[key]);
}
