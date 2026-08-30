import axios, { type InternalAxiosRequestConfig } from 'axios';
import type { ErrorResponse } from '@/types/api';
import { recordFailedRequest } from '@/utils/debugRingBuffer';

const RETRY_MAX_ATTEMPTS = 3;
const RETRY_DELAY_MS_INITIAL = 1000;
const RETRY_DELAY_MS_MAX = 10000;

/**
 * Timeouts for calls that legitimately run longer than the default. Anything
 * not listed here uses the default below.
 *
 * `NONE` (0) disables the timeout entirely and is reserved for uploads that
 * report `onUploadProgress`: the progress callback is the sign of life, and a
 * large file over Wi-Fi has no upper bound worth guessing.
 */
export const TIMEOUT = {
  /** No timeout - only for uploads with a progress callback. */
  NONE: 0,
  /** Host-Helper actions that shell out and wait: scans, pairing, connects. */
  HOST_ACTION: 30_000,
  /** Cover and logo uploads. nginx cuts the connection at 120s anyway. */
  UPLOAD: 120_000,
  /** Backup restore and USB import: copying, unpacking, restarting. */
  LONG_RUNNING: 180_000,
} as const;

function isRetryable(error: {
  response?: { status: number };
  request?: unknown;
  config?: InternalAxiosRequestConfig;
}): boolean {
  if (!error.config) return false;
  const config = error.config as InternalAxiosRequestConfig & { __retryCount?: number };
  if ((config.__retryCount ?? 0) >= RETRY_MAX_ATTEMPTS) return false;
  const method = (error.config.method ?? 'get').toLowerCase();
  const hasResponse = !!error.response;
  const networkError = !hasResponse && !!error.request;

  // Only GET and HEAD may be repeated. A timeout, a dropped Wi-Fi link and a
  // 502 all look the same from here - a request without an answer - so a
  // retried POST can very well have reached the backend and been carried out.
  // Repeating it would upload the same file twice or restore a backup twice.
  const idempotent = method === 'get' || method === 'head';
  if (!idempotent) return false;

  if (networkError) return true;
  if (!hasResponse) return false;
  const status = error.response!.status;
  return status >= 500 || status === 408;
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export const apiClient = axios.create({
  baseURL: '/api/v1',
  // Enough for every plain JSON call. Uploads and host actions set their own
  // value from TIMEOUT above; see docs/services/webui/Architecture.md.
  timeout: 15_000,
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
});

apiClient.interceptors.request.use((config) => {
  (config as InternalAxiosRequestConfig & { __startedAt?: number }).__startedAt = Date.now();
  return config;
});

let onUnauthorized: (() => void) | null = null;
export function setOnUnauthorized(cb: (() => void) | null): void {
  onUnauthorized = cb;
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401 && onUnauthorized) {
      onUnauthorized();
    }

    const config = error.config as (InternalAxiosRequestConfig & { __retryCount?: number }) | undefined;
    const retryCount = config?.__retryCount ?? 0;

    if (config && isRetryable(error)) {
      config.__retryCount = retryCount + 1;
      const backoff = Math.min(
        RETRY_DELAY_MS_INITIAL * 2 ** retryCount,
        RETRY_DELAY_MS_MAX
      );
      await delay(backoff);
      return apiClient.request(config);
    }

    // Record the failure for the debug export before it is handed on. Only
    // the final outcome lands here, not each retry.
    const startedAt = (config as (InternalAxiosRequestConfig & { __startedAt?: number }) | undefined)?.__startedAt;
    recordFailedRequest({
      method: (config?.method ?? 'get').toUpperCase(),
      url: config?.url ?? 'unknown',
      status: error.response?.status,
      durationMs: startedAt ? Date.now() - startedAt : undefined,
      message: error.message,
    });

    if (error.response) {
      const errorData = error.response.data as ErrorResponse;
      console.error('[WebUI] API Error:', errorData?.error || error.response.data);
    } else if (error.request) {
      console.error('[WebUI] Network Error:', error.message);
    } else {
      console.error('[WebUI] Request Error:', error.message);
    }
    return Promise.reject(error);
  }
);

export default apiClient;
