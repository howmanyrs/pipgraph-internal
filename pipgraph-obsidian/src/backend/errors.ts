/**
 * Discriminated union of errors the client can produce.
 *
 * UI code switches on `kind` to decide how to render — e.g. a "Backend
 * unreachable?" banner for `network`, a toast for `http`, etc.
 *
 * Distinct from pipgraph-web/src/lib/api.ts which uses a single flat ApiError;
 * the plugin needs finer granularity because the panel surfaces a connectivity
 * indicator separate from per-action error toasts.
 */

export type PipGraphApiErrorKind =
  // Could not reach the server at all: DNS failure, refused connection,
  // offline, or Obsidian requestUrl threw before getting a response.
  | "network"
  // Got a response but it was a 4xx/5xx, OR the envelope returned
  // `{success: false}`. `status` reflects the HTTP status (200 for envelope
  // failures). `message` carries the backend's `error` field when present.
  | "http"
  // Response body was not valid JSON, or did not match the expected shape.
  | "parse"
  // Request exceeded the configured timeout.
  | "timeout";

interface BaseApiError {
  kind: PipGraphApiErrorKind;
  message: string;
  url?: string;
}

export interface NetworkApiError extends BaseApiError {
  kind: "network";
  cause?: unknown;
}

export interface HttpApiError extends BaseApiError {
  kind: "http";
  status: number;
  body?: string;
}

export interface ParseApiError extends BaseApiError {
  kind: "parse";
  body?: string;
  cause?: unknown;
}

export interface TimeoutApiError extends BaseApiError {
  kind: "timeout";
  timeoutMs: number;
}

export type PipGraphApiErrorPayload =
  | NetworkApiError
  | HttpApiError
  | ParseApiError
  | TimeoutApiError;

/**
 * Concrete Error subclass. We keep both shapes (discriminated payload +
 * thrown Error) because (a) `throw` requires Error semantics and (b) UI
 * code wants `switch(err.kind)`. The instance carries the payload fields
 * directly, so consumers do `catch (err) { if (err instanceof PipGraphApiError && err.kind === 'network') ... }`.
 */
export class PipGraphApiError extends Error {
  readonly kind: PipGraphApiErrorKind;
  readonly url?: string;
  readonly status?: number;
  readonly body?: string;
  readonly timeoutMs?: number;
  readonly cause?: unknown;

  constructor(payload: PipGraphApiErrorPayload) {
    super(payload.message);
    this.name = "PipGraphApiError";
    this.kind = payload.kind;
    this.url = payload.url;
    if (payload.kind === "http") {
      this.status = payload.status;
      this.body = payload.body;
    } else if (payload.kind === "parse") {
      this.body = payload.body;
      this.cause = payload.cause;
    } else if (payload.kind === "timeout") {
      this.timeoutMs = payload.timeoutMs;
    } else if (payload.kind === "network") {
      this.cause = payload.cause;
    }
  }
}

export function isPipGraphApiError(err: unknown): err is PipGraphApiError {
  return err instanceof PipGraphApiError;
}
