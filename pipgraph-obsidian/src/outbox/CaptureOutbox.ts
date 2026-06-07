import { Notice, TFolder } from "obsidian";
import type PipGraphPlugin from "../main";
import { getDraftsPath, getInboxPath } from "../settings/PipGraphSettings";
import { resolveUniqueFilePath, sanitiseForFilename } from "../vault/paths";
import {
  PipGraphApiError,
  isFailedStatus,
  isSettledStatus,
  type EpisodicNode,
} from "../backend";

const POLL_INTERVAL_MS = 1500;
const POLL_MAX_ATTEMPTS = 60; // ~90s ceiling while the naming job runs

/** The two pre-materialisation states a capture can be parked in (Model 2). */
type CaptureState = "inflight" | "failed-create";

/** An in-memory record backing a phantom row in the Inbox tab. */
export interface CaptureRecord {
  uuid: string;
  /** Preview label derived from the note's first line. */
  preview: string;
  content: string;
  state: CaptureState;
}

/**
 * Durable capture outbox (process-queue P1b + inbox-in-process Model 2).
 *
 * Capture must not block on the backend's LLM naming call, and a captured note
 * must never be lost — even if Obsidian or the backend dies mid-flight. So each
 * capture is first written as a *hidden* pending file under the plugin folder
 * (`<plugin-dir>/pending/<uuid>.md`, **body only** — the UUID lives in the
 * filename, not in frontmatter). That file is the durable outbox record: it is
 * invisible in the explorer (it lives under `.obsidian/`, which Obsidian neither
 * shows nor indexes) and it survives restarts.
 *
 * **Visibility (Model 2).** Alongside the durable pending file, the outbox keeps
 * an in-memory {@link CaptureRecord} per capture so the Inbox tab can show a
 * **phantom row** for the two pre-materialisation states:
 *   - `inflight`     — POST sent, naming job running (a static `⟳`).
 *   - `failed-create`— the create never reached the graph (backend unreachable),
 *     so there is no node yet (a `⚠`, retriable).
 * A *materialised* note (happy or fallback) is a **real file**, not a phantom —
 * the record is dropped the moment it lands. A fallback-named file is flagged
 * separately by the {@link NamingTracker} (`❗`), not held here.
 *
 * Delivery runs in the background, per uuid:
 *   1. POST /episode { content, uuid, generate_name: true } — idempotent (the
 *      server MERGEs on uuid), so retries never duplicate.
 *   2. Poll GET /episodic/{uuid} until the naming job settles — status cleared
 *      (real LLM name) **or** `failed:generate_episode_name` (a fallback name).
 *   3. Materialise the note into the Inbox *once*, named from the node; on a
 *      fallback also register it with the NamingTracker (`❗`).
 *   4. Delete the pending file (outbox record consumed).
 *
 * On plugin load, {@link reconcile} rescans the pending folder. **No auto-POST**
 * (Decision OQ-2): it only *finishes what the backend already did* — materialise
 * settled/fallback nodes locally — and surfaces everything still unfinished
 * (job lost mid-naming, or no node at all) as the same retriable `failed-create`
 * phantom for the user to retry / save / discard.
 *
 * Note (Decision, 2026-06-04): the UUID is recovered from the pending filename,
 * so we do not write `pipgraph.uuid` into any note's frontmatter — E3
 * (uuid-primary identity) stays deferred. The materialised Inbox note is linked
 * to its Episodic via `file_path`, as elsewhere.
 */
export class CaptureOutbox {
  private readonly plugin: PipGraphPlugin;
  /** Phantom-backing records, newest-last (the Inbox tab renders newest-first). */
  private readonly records = new Map<string, CaptureRecord>();
  /**
   * uuids whose delivery is currently running — guards against double-delivery
   * (e.g. a retry firing while a live delivery is already in flight).
   */
  private readonly running = new Set<string>();

  /** Fired whenever the records change (drives the statusbar + Inbox tab). */
  onChange: (() => void) | null = null;

  constructor(plugin: PipGraphPlugin) {
    this.plugin = plugin;
  }

  /** In-flight captures — what the statusbar counter shows (fallbacks excluded). */
  get pendingCount(): number {
    let n = 0;
    for (const r of this.records.values()) if (r.state === "inflight") n++;
    return n;
  }

  /** Snapshot of the phantom records, newest-first, for the Inbox tab. */
  listRecords(): CaptureRecord[] {
    return [...this.records.values()].reverse();
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
    this.records.set(uuid, {
      uuid,
      preview: previewOf(content),
      content,
      state: "inflight",
    });
    this.onChange?.();
    void this.deliver(uuid);
  }

  /**
   * Rescan pending records on load and reconcile against the backend — **without
   * any auto-POST** (Decision OQ-2). Finished work (named/fallback) is
   * materialised locally; everything unfinished becomes a retriable phantom.
   */
  async reconcile(): Promise<void> {
    const adapter = this.plugin.app.vault.adapter;
    const dir = this.pendingDir();
    if (!(await adapter.exists(dir))) return;

    const listing = await adapter.list(dir);
    for (const filePath of listing.files) {
      if (!filePath.endsWith(".md")) continue;
      const uuid = basenameUuid(filePath);
      if (!uuid || this.running.has(uuid) || this.records.has(uuid)) continue;
      let content: string;
      try {
        content = await adapter.read(filePath);
      } catch {
        continue; // unreadable record — leave it, retry on next load
      }

      let episodic: EpisodicNode | null = null;
      try {
        episodic = await this.plugin.client.getEpisodicByUuid(uuid);
      } catch {
        episodic = null; // backend unreachable → treat as unfinished (⚠ below)
      }

      if (episodic && (isSettledStatus(episodic.status) || isFailedStatus(episodic.status))) {
        // The backend already finished naming (real or fallback). Finish the
        // happy/fallback path locally — no POST.
        try {
          const path = await this.materialise(uuid, episodic, content);
          if (isFailedStatus(episodic.status)) {
            this.plugin.naming.markFallback(uuid, path);
          }
          await this.removePending(uuid);
        } catch {
          // Materialisation failed — surface it as a retriable phantom.
          this.addFailedCreate(uuid, content);
        }
        continue;
      }

      // Unfinished: the naming job was lost mid-flight, or no node exists. Both
      // collapse to the same retriable ⚠ phantom — Retry re-POSTs (idempotent),
      // Save/Discard deleteNode best-effort (a no-op when there is no node).
      this.addFailedCreate(uuid, content);
    }
  }

  /**
   * Danger-zone reset: drop every in-memory record and delete all durable
   * pending files (`<plugin-dir>/pending/*.md`). Does **not** touch the graph —
   * the caller wipes that separately. Returns the number of pending files
   * removed. Best-effort: unreadable/locked files are skipped.
   */
  async purgePending(): Promise<number> {
    this.records.clear();
    const adapter = this.plugin.app.vault.adapter;
    const dir = this.pendingDir();
    let removed = 0;
    if (await adapter.exists(dir)) {
      const listing = await adapter.list(dir);
      for (const filePath of listing.files) {
        try {
          await adapter.remove(filePath);
          removed++;
        } catch {
          // leave a stubborn file; the user can clear it manually
        }
      }
    }
    this.onChange?.();
    return removed;
  }

  // -- per-record user actions (Inbox tab context menu) -----------------------

  /** Retry a failed-create capture: re-run delivery from the top. */
  retry(uuid: string): void {
    const record = this.records.get(uuid);
    if (!record) return;
    record.state = "inflight";
    this.onChange?.();
    void this.deliver(uuid);
  }

  /**
   * Move a failed-create capture out of the inbox into the drafts folder, and
   * best-effort delete any graph node (honouring "не в базе"). Drops the pending
   * record + phantom.
   */
  async saveToDraft(uuid: string): Promise<void> {
    const record = this.records.get(uuid);
    if (!record) return;
    try {
      const draftsPath = getDraftsPath(this.plugin.settings);
      await this.ensureFolder(draftsPath);
      const base = sanitiseForFilename(record.preview);
      const path = resolveUniqueFilePath(this.plugin.app.vault, draftsPath, base);
      await this.plugin.app.vault.create(path, record.content);
      new Notice(`PipGraph: saved a captured note to drafts ("${base}").`);
    } catch (err) {
      new Notice(`PipGraph: couldn't save to drafts: ${describeError(err)}`);
      return; // keep the phantom so the note isn't lost
    }
    await this.bestEffortDeleteNode(uuid);
    await this.discardRecord(uuid);
  }

  /** Discard a failed-create capture entirely (best-effort node delete). */
  async discard(uuid: string): Promise<void> {
    if (!this.records.has(uuid)) return;
    await this.bestEffortDeleteNode(uuid);
    await this.discardRecord(uuid);
  }

  // -- delivery ---------------------------------------------------------------

  private async deliver(uuid: string): Promise<void> {
    if (this.running.has(uuid)) return;
    const record = this.records.get(uuid);
    if (!record) return;
    const content = record.content;
    this.running.add(uuid);
    try {
      // 1. Idempotent create (MERGE on uuid) + enqueue the async naming job.
      try {
        await this.plugin.client.createEpisode({
          content,
          uuid,
          generate_name: true,
        });
      } catch (err) {
        // The POST never created a node — park as a retriable phantom (no node).
        record.state = "failed-create";
        this.onChange?.();
        new Notice(
          `PipGraph: couldn't add a note (${describeError(err)}). ` +
            `It's saved — retry from the Inbox panel.`,
        );
        return;
      }

      // 2. Poll until the naming job settles (real name OR fallback).
      const episodic = await this.pollUntilSettled(uuid);
      if (!episodic) return; // timed out — leave the in-flight phantom for reconcile

      // 3. Materialise into the Inbox exactly once.
      const path = await this.materialise(uuid, episodic, content);
      if (isFailedStatus(episodic.status)) {
        // Fallback name: the file lands, but flag it (`❗`) for regenerate.
        this.plugin.naming.markFallback(uuid, path);
      }

      // 4. Phantom→file swap: drop the record first, then notify (so the tab
      //    shows the real file row, never a phantom + file together).
      this.records.delete(uuid);
      this.onChange?.();
      await this.removePending(uuid);
    } finally {
      this.running.delete(uuid);
    }
  }

  /**
   * Poll until the naming job settles. Resolves with the node on a cleared
   * status (real LLM name) **or** `failed:generate_episode_name` (a fallback
   * name) — both materialise. Returns null only on timeout, leaving the
   * in-flight phantom for the next reconcile.
   */
  private async pollUntilSettled(uuid: string): Promise<EpisodicNode | null> {
    for (let attempt = 0; attempt < POLL_MAX_ATTEMPTS; attempt++) {
      const episodic = await this.plugin.client.getEpisodicByUuid(uuid);
      if (episodic) {
        // Settled (real name) or failed (fallback name) — both have a usable
        // name on the node, so materialise either way.
        if (isSettledStatus(episodic.status) || isFailedStatus(episodic.status)) {
          return episodic;
        }
      }
      // still generating a name (or not yet visible) — wait and retry
      await sleep(POLL_INTERVAL_MS);
    }
    return null; // timed out — leave the in-flight phantom for a later retry
  }

  /**
   * Materialise an Episodic into the Inbox exactly once, naming the file from the
   * node. Returns the final (collision-resolved) vault path. Never touches
   * `status`, so a fallback node's `failed:generate_episode_name` survives.
   */
  private async materialise(
    uuid: string,
    episodic: EpisodicNode,
    content: string,
  ): Promise<string> {
    // Crash-recovery guard: a non-empty file_path means this episode was already
    // materialised on an earlier run (we crashed before deleting the pending
    // file). Don't create a duplicate — just report the existing path.
    if (episodic.file_path) {
      return episodic.file_path;
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
    return path;
  }

  // -- record/state helpers ---------------------------------------------------

  private addFailedCreate(uuid: string, content: string): void {
    this.records.set(uuid, {
      uuid,
      preview: previewOf(content),
      content,
      state: "failed-create",
    });
    this.onChange?.();
  }

  /** Drop the in-memory record + the durable pending file, then notify. */
  private async discardRecord(uuid: string): Promise<void> {
    this.records.delete(uuid);
    await this.removePending(uuid);
    this.onChange?.();
  }

  /** Best-effort node delete — honours "not in the DB"; a no-op when no node. */
  private async bestEffortDeleteNode(uuid: string): Promise<void> {
    try {
      await this.plugin.client.deleteNode(uuid);
    } catch {
      // No node (failed-create) or backend hiccup — nothing to clean up here.
    }
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

/** First non-empty line, stripped of markdown, collapsed, ~50 chars + `…`. */
function previewOf(content: string): string {
  const firstLine =
    content
      .split("\n")
      .map((l) => l.trim())
      .find((l) => l.length > 0) ?? "";
  const stripped = firstLine.replace(/[#*`[\]]+/g, "").replace(/\s+/g, " ").trim();
  if (!stripped) return "Untitled note";
  return stripped.length > 50 ? `${stripped.slice(0, 50)}…` : stripped;
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
