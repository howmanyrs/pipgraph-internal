import { Notice, TFile, TFolder } from "obsidian";
import type PipGraphPlugin from "../main";
import {
  getDraftsPath,
  getInboxPath,
} from "../settings/PipGraphSettings";
import { NewInboxNoteModal } from "../modals/NewInboxNoteModal";
import { PipGraphApiError } from "../backend";

export function registerCommands(plugin: PipGraphPlugin): void {
  plugin.addCommand({
    id: "open-triage-panel",
    name: "Open triage panel",
    callback: () => {
      void plugin.activateTriagePanel();
    },
  });

  plugin.addCommand({
    id: "new-inbox-note",
    name: "New inbox note",
    callback: () => {
      new NewInboxNoteModal(plugin).open();
    },
  });

  plugin.addCommand({
    id: "draft-inbox-note",
    name: "New draft inbox note",
    callback: () => {
      void createDraftNote(plugin);
    },
  });

  plugin.addCommand({
    id: "process-current-draft",
    name: "Process current draft",
    checkCallback: (checking) => {
      const file = plugin.app.workspace.getActiveFile();
      const draftsPath = `${getDraftsPath(plugin.settings)}/`;
      const isDraft =
        file !== null &&
        file.extension === "md" &&
        file.path.startsWith(draftsPath);
      if (!isDraft) return false;
      if (checking) return true;
      void processDraft(plugin, file!);
      return true;
    },
  });

  plugin.addCommand({
    id: "refresh-triage",
    name: "Refresh triage queue",
    callback: () => {
      new Notice("Refresh triage queue: not implemented yet — coming in M6.");
    },
  });

  plugin.addCommand({
    id: "sync-from-backend",
    name: "Sync from backend",
    callback: () => {
      new Notice("Sync from backend: not implemented yet — coming in M4.");
    },
  });

  plugin.addCommand({
    id: "auto-process-inbox",
    name: "Auto-process inbox",
    callback: () => {
      new Notice(
        "Auto-process inbox: not implemented yet — coming in M8 Phase 1.",
      );
    },
  });
}

async function createDraftNote(plugin: PipGraphPlugin): Promise<void> {
  const { app } = plugin;
  const draftsPath = getDraftsPath(plugin.settings);

  const existing = app.vault.getAbstractFileByPath(draftsPath);
  if (existing && !(existing instanceof TFolder)) {
    new Notice(`"${draftsPath}" exists but is not a folder.`);
    return;
  }
  if (!existing) {
    try {
      await app.vault.createFolder(draftsPath);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      new Notice(`Failed to create drafts folder: ${message}`);
      return;
    }
  }

  const stamp = new Date()
    .toISOString()
    .replace(/[:.]/g, "")
    .replace("T", "-");
  const path = `${draftsPath}/Draft-${stamp}.md`;

  let file: TFile;
  try {
    file = await app.vault.create(path, "");
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    new Notice(`Failed to create draft: ${message}`);
    return;
  }

  await app.workspace.getLeaf(false).openFile(file);
}

async function processDraft(
  plugin: PipGraphPlugin,
  file: TFile,
): Promise<void> {
  const { app } = plugin;
  const body = await app.vault.read(file);
  if (!body.trim()) {
    new Notice("Draft is empty — type something before processing.");
    return;
  }

  const inboxPath = getInboxPath(plugin.settings);
  const targetPath = `${inboxPath}/${file.name}`;
  if (app.vault.getAbstractFileByPath(targetPath)) {
    new Notice(
      `Cannot move draft: "${targetPath}" already exists. Rename the draft first.`,
    );
    return;
  }

  try {
    await plugin.client.createEpisode({
      name: file.basename,
      content: body,
      file_path: targetPath,
      source_description: "obsidian:process-draft",
    });
  } catch (err) {
    new Notice(`Failed to process draft: ${describeError(err)}`);
    return;
  }

  try {
    await app.fileManager.renameFile(file, targetPath);
  } catch (err) {
    new Notice(
      `Episodic created in Neo4j, but moving the file failed: ${describeError(err)}`,
    );
    return;
  }

  new Notice("Draft processed.");
}

function describeError(err: unknown): string {
  if (err instanceof PipGraphApiError) {
    if (err.kind === "network") return "backend unreachable";
    if (err.kind === "timeout") return "backend timed out";
    return err.message;
  }
  return err instanceof Error ? err.message : String(err);
}
