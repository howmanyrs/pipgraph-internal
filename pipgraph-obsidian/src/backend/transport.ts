/**
 * Transport seam between the client and the actual HTTP layer.
 *
 * Why a seam:
 *  - Production runs inside Obsidian and uses `requestUrl` from the obsidian
 *    API; that bypasses CORS for localhost backends (a fetch() call would hit
 *    preflight issues).
 *  - Tests and ad-hoc debugging want to inject a fake (e.g. returning canned
 *    JSON) without monkey-patching globals.
 *
 * Reference: pipgraph-web uses raw global fetch() — fine in a browser tab,
 * not fine in Obsidian (CORS) and inflexible for mocking.
 *
 * The Fetcher contract is intentionally minimal: caller hands in url/method/
 * headers/body/timeout, gets back `{status, body}` or a `PipGraphApiError`.
 * Envelope parsing and 2xx checks live in PipGraphClient, not here.
 */

import { requestUrl, type RequestUrlParam } from "obsidian";
import { PipGraphApiError } from "./errors";

export interface RequestSpec {
  url: string;
  method: "GET" | "POST" | "DELETE" | "PUT" | "PATCH";
  headers: Record<string, string>;
  body?: string;
  timeoutMs: number;
}

export interface RawResponse {
  status: number;
  body: string;
}

export type Fetcher = (spec: RequestSpec) => Promise<RawResponse>;

/**
 * Default fetcher: Obsidian's requestUrl wrapped with a Promise.race timeout.
 *
 * Note: requestUrl has no native abort. On timeout we reject and abandon
 * the underlying request — bytes may still complete in the background.
 * Acceptable for v1; revisit if it becomes visible.
 */
export const obsidianFetcher: Fetcher = async (spec) => {
  const params: RequestUrlParam = {
    url: spec.url,
    method: spec.method,
    headers: spec.headers,
    body: spec.body,
    // Don't let requestUrl throw on non-2xx — we want to surface the status
    // ourselves and let the client classify it.
    throw: false,
  };

  const requestPromise = (async (): Promise<RawResponse> => {
    try {
      const res = await requestUrl(params);
      return { status: res.status, body: res.text };
    } catch (cause) {
      // requestUrl only throws on transport-level failures when throw:false —
      // typically network unreachable, DNS, refused connection.
      throw new PipGraphApiError({
        kind: "network",
        message: cause instanceof Error ? cause.message : String(cause),
        url: spec.url,
        cause,
      });
    }
  })();

  const timeoutPromise = new Promise<never>((_, reject) => {
    setTimeout(() => {
      reject(
        new PipGraphApiError({
          kind: "timeout",
          message: `Request to ${spec.url} timed out after ${spec.timeoutMs}ms`,
          url: spec.url,
          timeoutMs: spec.timeoutMs,
        }),
      );
    }, spec.timeoutMs);
  });

  return Promise.race([requestPromise, timeoutPromise]);
};
