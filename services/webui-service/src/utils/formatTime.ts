/**
 * Format milliseconds to "MM:SS" or "HH:MM:SS"
 */
export function formatTime(ms: number | null | undefined): string {
  if (ms == null || ms < 0) return '0:00';

  const totalSeconds = Math.floor(ms / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;

  const pad = (n: number) => String(n).padStart(2, '0');

  if (hours > 0) {
    return `${hours}:${pad(minutes)}:${pad(seconds)}`;
  }
  return `${minutes}:${pad(seconds)}`;
}

/**
 * Format seconds to human-readable uptime string
 */
export function formatUptime(seconds: number | null | undefined): { hours: number; minutes: number } {
  if (seconds == null) return { hours: 0, minutes: 0 };
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return { hours, minutes };
}

/**
 * Format a timestamp as a relative time ("vor 5 Minuten", "gestern", ...).
 *
 * Die Einheit waechst mit dem Abstand, statt alles in einer festen Einheit zu
 * zeigen – "vor 203.844 Minuten" ist fuer niemanden lesbar. Schwellen:
 *   < 1 Minute  -> "gerade eben" (numeric: 'auto')
 *   < 60 Minuten-> Minuten
 *   < 24 Stunden-> Stunden
 *   < 30 Tage   -> Tage (numeric: 'auto' liefert "gestern")
 *   < 12 Monate -> Monate
 *   sonst       -> Jahre
 *
 * @param value ISO-Zeitstempel (oder Date/ms). Ohne Zeitzone wird UTC angenommen,
 *              weil das Backend naive UTC-Zeitstempel serialisiert.
 * @param locale BCP-47 Sprache, i. d. R. `i18n.language`
 */
export function formatRelativeTime(
  value: string | number | Date | null | undefined,
  locale?: string
): string | null {
  const date = parseTimestamp(value);
  if (date === null) return null;

  const diffMs = Date.now() - date.getTime();
  // Zukunft (Uhr-Drift zwischen Box und Browser) nicht als "in 3 Minuten" zeigen.
  const elapsedMs = Math.max(0, diffMs);

  const rtf = new Intl.RelativeTimeFormat(locale || undefined, { numeric: 'auto' });

  const minutes = elapsedMs / 60_000;
  if (minutes < 1) return rtf.format(0, 'second');
  if (minutes < 60) return rtf.format(-Math.round(minutes), 'minute');

  const hours = minutes / 60;
  if (hours < 24) return rtf.format(-Math.round(hours), 'hour');

  const days = hours / 24;
  if (days < 30) {
    // Ueber Kalendertage statt verstrichene Stunden: numeric 'auto' macht aus
    // -1/-2 "gestern"/"vorgestern", und das muss zum Datum passen. 33 Stunden
    // her ist verstrichen "1 Tag", kalendarisch aber vorgestern.
    return rtf.format(-calendarDaysBetween(date, new Date()), 'day');
  }

  const months = days / 30.44;
  if (months < 12) return rtf.format(-Math.round(months), 'month');

  return rtf.format(-Math.round(days / 365.25), 'year');
}

/**
 * Parse a backend timestamp. Zeitstempel ohne Zonen-Suffix werden als UTC
 * gelesen – sonst verschiebt die lokale Zeitzone das Ergebnis um Stunden.
 */
function parseTimestamp(value: string | number | Date | null | undefined): Date | null {
  if (value == null) return null;
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value;

  let date: Date;
  if (typeof value === 'number') {
    date = new Date(value);
  } else {
    const trimmed = value.trim();
    if (!trimmed) return null;
    const hasZone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(trimmed);
    date = new Date(hasZone ? trimmed : `${trimmed}Z`);
  }
  return Number.isNaN(date.getTime()) ? null : date;
}

/**
 * Format a backend timestamp as an absolute local date/time – gedacht als
 * Tooltip zur relativen Angabe, wenn jemand das genaue Datum sehen will.
 */
export function formatAbsoluteTime(
  value: string | number | Date | null | undefined,
  locale?: string
): string | null {
  const date = parseTimestamp(value);
  if (date === null) return null;
  return date.toLocaleString(locale || undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/** Whole calendar days between two local dates (midnight to midnight). */
function calendarDaysBetween(from: Date, to: Date): number {
  const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  return Math.round((startOfDay(to) - startOfDay(from)) / 86_400_000);
}
