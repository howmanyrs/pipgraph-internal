import { Notice, TFolder } from "obsidian";
import type PipGraphPlugin from "../main";
import { getInboxPath } from "../settings/PipGraphSettings";
import { resolveUniqueFilePath, sanitiseForFilename } from "../vault/paths";
import { PipGraphApiError, type EpisodicNode } from "../backend";

const POLL_INTERVAL_MS = 1500;
const POLL_MAX_ATTEMPTS = 60; // ~90s ceiling while the naming job runs

/**
 * Durable capture outbox (process-queue P1b).
 *
 * Capture must not block on the backend's LLM naming call, and a captured note
 * must never be lost — even if Obsidian or the backend dies mid-flight. So each
 * capture is first written as a *hidden* pending file under the plugin folder
 * (`<plugin-dir>/pending/<uuid>.md`, **body only** — the UUID lives in the
 * filename, not in frontmatter). That file is the durable outbox record: it is
 * invisible in the explorer (it lives under `.obsidian/`, which Obsidian neither
 * shows nor indexes) and it survives restarts.
 *
 * Delivery then runs in the background, per uuid:
 *   1. POST /episode { content, uuid, generate_name: true } — idempotent (the
 *      server MERGEs on uuid), so retries never duplicate.
 *   2. Poll GET /episodic/{uuid} until `status` clears (naming job finished).
 *   3. Materialise the note into the Inbox *once*, with the LLM name, and record
 *      its path back (PATCH file_path, first-bind — guard E6 allows None→set).
 *   4. Delete the pending file (outbox record consumed).
 *
 * On plugin load, {@link reconcile} rescans the pending folder and resumes
 * delivery for anything a crash left behind.
 *
 * Note (Decision, 2026-06-04): the UUID is recovered from the pending filename,
 * so we do not write `pipgraph.uuid` into any note's frontmatter — E3
 * (uuid-primary identity) stays deferred. The materialised Inbox note is linked
 * to its Episodic via `file_path`, as elsewhere.
 */
export class CaptureOutbox {
  private readonly plugin: PipGraphPlugin;
  /**
   * uuids whose delivery is in flight — guards against double-delivery (e.g. a
   * reconcile scanning a record whose live delivery is already running).
   */
  private readonly inFlight = new Set<string>();

  /** Fired whenever {@link pendingCount} changes (drives the statusbar). */
  onChange: (() => void) | null = null;

  constructor(plugin: PipGraphPlugin) {
    this.plugin = plugin;
  }

  /** Records currently being delivered — what the statusbar counter shows. */
  get pendingCount(): number {
    return this.inFlight.size;
  }

  /**
   * Durably capture a note: write the pending file synchronously (so the caller
   * can close the modal knowing the note is safe), then kick off background
   * delivery. Throws only if the durable write itself fails — the caller should
   * surface that and keep the note's text on screen.
   */
  async enqueue(content: string): Promise<void> {
    const uuid = crypto.randomUUID();
    await this.writePending(uuid, content);
    void this.deliver(uuid, content);
  }

  /** Re-deliver any pending records left on disk (called once on plugin load). */
  async reconcile(): Promise<void> {
    const adapter = this.plugin.app.vault.adapter;
    const dir = this.pendingDir();
    if (!(await adapter.exists(dir))) return;

    const listing = await adapter.list(dir);
    for (const filePath of listing.files) {
      if (!filePath.endsWith(".md")) continue;
      const uuid = basenameUuid(filePath);
      if (!uuid || this.inFlight.has(uuid)) continue;
      let content: string;
      try {
        content = await adapter.read(filePath);
      } catch {
        continue; // unreadable record — leave it, retry on next load
      }
      void this.deliver(uuid, content);
    }
  }

  // -- delivery ---------------------------------------------------------------

  private async deliver(uuid: string, content: string): Promise<void> {
    if (this.inFlight.has(uuid)) return;
    this.inFlight.add(uuid);
    this.onChange?.();
    try {
      // 1. Idempotent create (MERGE on uuid) + enqueue the async naming job.
      await this.plugin.client.createEpisode({
        content,
        uuid,
        generate_name: true,
      });

      // 2. Poll until the naming job clears `status`.
      const episodic = await this.pollUntilSettled(uuid);
      if (!episodic) return; // failed/timed-out — pending file stays for retry

      // 3. Materialise into the Inbox exactly once.
      await this.materialise(uuid, episodic, content);

      // 4. Outbox record consumed.
      await this.removePending(uuid);
    } catch (err) {
      // Leave the pending file in place: it is retried on the next reconcile
      // (plugin reload). The user's note is not lost.
      new Notice(
        `PipGraph: couldn't finish capturing a note (${describeError(err)}). ` +
          `It's saved and will retry when you reload the plugin.`,
      );
    } finally {
      this.inFlight.delete(uuid);
      this.onChange?.();
    }
  }

  private async pollUntilSettled(uuid: string): Promise<EpisodicNode | null> {
    for (let attempt = 0; attempt < POLL_MAX_ATTEMPTS; attempt++) {
      const episodic = await this.plugin.client.getEpisodicByUuid(uuid);
      if (episodic) {
        if (episodic.status === "failed") {
          new Notice("PipGraph: naming failed for a captured note.");
          return null;
        }
        if (!episodic.status) return episodic; // settled → done
      }
      // still processing (or not yet visible) — wait and retry
      await sleep(POLL_INTERVAL_MS);
    }
    return null; // timed out — leave the pending record for a later retry
  }

  private async materialise(
    uuid: string,
    episodic: EpisodicNode,
    content: string,
  ): Promise<void> {
    // Crash-recovery guard: a non-empty file_path means this episode was already
    // materialised on an earlier run (we crashed before deleting the pending
    // file). Don't create a duplicate — just drop the stale record.
    if (episodic.file_path) {
      await this.removePending(uuid);
      return;
    }

    const inboxPath = getInboxPath(this.plugin.settings);
    await this.ensureFolder(inboxPath);

    const baseName = sanitiseForFilename(episodic.name);
    const path = resolveUniqueFilePath(
      this.plugin.app.vault,
      inboxPath,
      baseName,
    );

    await this.plugin.app.vault.create(path, content);

    // Record the collision-resolved path back on the node (first-bind, E2).
    // Best-effort: the file already exists, so a PATCH failure just leaves the
    // node's file_path null until a later sync — the note itself is safe.
    try {
      await this.plugin.client.updateEpisodic(uuid, { file_path: path });
    } catch (err) {
      new Notice(
        `PipGraph: note added, but recording its path failed: ${describeError(err)}`,
      );
    }

    new Notice(`PipGraph: added "${baseName}" to the inbox.`);
  }

  // -- pending-file plumbing --------------------------------------------------

  private pendingDir(): string {
    const base =
      this.plugin.manifest.dir ??
      `${this.plugin.app.vault.configDir}/plugins/${this.plugin.manifest.id}`;
    return `${base}/pending`;
  }

  private async writePending(uuid: string, content: string): Promise<void> {
    const adapter = this.plugin.app.vault.adapter;
    const dir = this.pendingDir();
    if (!(await adapter.exists(dir))) {
      await adapter.mkdir(dir);
    }
    await adapter.write(`${dir}/${uuid}.md`, content);
  }

  private async removePending(uuid: string): Promise<void> {
    const adapter = this.plugin.app.vault.adapter;
    const path = `${this.pendingDir()}/${uuid}.md`;
    if (await adapter.exists(path)) {
      await adapter.remove(path);
    }
  }

  private async ensureFolder(path: string): Promise<void> {
    const existing = this.plugin.app.vault.getAbstractFileByPath(path);
    if (existing instanceof TFolder) return;
    if (existing) {
      throw new Error(`"${path}" exists but is not a folder.`);
    }
    await this.plugin.app.vault.createFolder(path);
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Recover the capture UUID from a `<uuid>.md` pending-file path. */
function basenameUuid(filePath: string): string | null {
  const file = filePath.split("/").pop();
  if (!file) return null;
  return file.replace(/\.md$/, "");
}

function describeError(err: unknown): string {
  if (err instanceof PipGraphApiError) {
    switch (err.kind) {
      case "network":
        return "backend unreachable";
      case "timeout":
        return "backend timed out";
      case "http":
        return err.message;
      case "parse":
        return "unexpected response from backend";
    }
  }
  return err instanceof Error ? err.message : String(err);
}
