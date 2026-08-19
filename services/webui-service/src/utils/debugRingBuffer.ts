/**
 * Ring buffers for everything the WebUI knows and nobody else does.
 *
 * Frontend faults are invisible to the backend: a crashed render, a rejected
 * promise or a request that failed in the browser leaves no trace in any
 * container log. These buffers keep the last N of them in memory so the debug
 * export can carry them along.
 *
 * Memory only - nothing is persisted, so closing the tab clears it.
 */

const MAX_ENTRIES = 100;
const MAX_MESSAGE_CHARS = 500;
const MAX_STACK_CHARS = 2000;

export interface ClientErrorEntry {
  at: string;
  kind: 'error' | 'unhandledrejection';
  message: string;
  source?: string;
  line?: number;
  column?: number;
  stack?: string;
}

export interface FailedRequestEntry {
  at: string;
  method: string;
  url: string;
  status?: number;
  durationMs?: number;
  message?: string;
}

export interface ClientContext {
  browser: Record<string, unknown>;
  console_errors: ClientErrorEntry[];
  failed_requests: FailedRequestEntry[];
}

class RingBuffer<T> {
  private items: T[] = [];

  constructor(private readonly limit: number) {}

  push(item: T): void {
    this.items.push(item);
    if (this.items.length > this.limit) {
      this.items.splice(0, this.items.length - this.limit);
    }
  }

  entries(): T[] {
    return [...this.items];
  }

  clear(): void {
    this.items = [];
  }
}

const errorBuffer = new RingBuffer<ClientErrorEntry>(MAX_ENTRIES);
const requestBuffer = new RingBuffer<FailedRequestEntry>(MAX_ENTRIES);

function truncate(value: unknown, max: number): string {
  const text = typeof value === 'string' ? value : String(value ?? '');
  return text.length > max ? `${text.slice(0, max)}…` : text;
}

export function recordClientError(entry: Omit<ClientErrorEntry, 'at'>): void {
  errorBuffer.push({
    ...entry,
    at: new Date().toISOString(),
    message: truncate(entry.message, MAX_MESSAGE_CHARS),
    stack: entry.stack ? truncate(entry.stack, MAX_STACK_CHARS) : undefined,
  });
}

export function recordFailedRequest(entry: Omit<FailedRequestEntry, 'at'>): void {
  requestBuffer.push({
    ...entry,
    at: new Date().toISOString(),
    message: entry.message ? truncate(entry.message, MAX_MESSAGE_CHARS) : undefined,
  });
}

let installed = false;

/** Capture uncaught errors and rejected promises. Safe to call more than once. */
export function installGlobalErrorCapture(): void {
  if (installed || typeof window === 'undefined') return;
  installed = true;

  window.addEventListener('error', (event) => {
    recordClientError({
      kind: 'error',
      message: event.message || 'Unbekannter Fehler',
      source: event.filename,
      line: event.lineno,
      column: event.colno,
      stack: event.error instanceof Error ? event.error.stack : undefined,
    });
  });

  window.addEventListener('unhandledrejection', (event) => {
    const reason = event.reason;
    recordClientError({
      kind: 'unhandledrejection',
      message: reason instanceof Error ? reason.message : String(reason),
      stack: reason instanceof Error ? reason.stack : undefined,
    });
  });
}

/**
 * Snapshot for the export. Deliberately narrow: browser capabilities and
 * viewport, never history, cookies or storage of other origins.
 */
export function collectClientContext(): ClientContext {
  const nav = typeof navigator === 'undefined' ? undefined : navigator;
  const win = typeof window === 'undefined' ? undefined : window;
  return {
    browser: {
      user_agent: nav?.userAgent,
      language: nav?.language,
      languages: nav?.languages,
      online: nav?.onLine,
      platform: (nav as unknown as { platform?: string })?.platform,
      viewport: win ? { width: win.innerWidth, height: win.innerHeight } : undefined,
      screen: win?.screen ? { width: win.screen.width, height: win.screen.height } : undefined,
      device_pixel_ratio: win?.devicePixelRatio,
      standalone_pwa: win?.matchMedia?.('(display-mode: standalone)')?.matches ?? false,
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      page_url: win?.location?.pathname,
      collected_at: new Date().toISOString(),
    },
    console_errors: errorBuffer.entries(),
    failed_requests: requestBuffer.entries(),
  };
}

export function clearDebugBuffers(): void {
  errorBuffer.clear();
  requestBuffer.clear();
}
