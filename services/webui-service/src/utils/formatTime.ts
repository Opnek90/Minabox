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
 * Format a timestamp as a relative time ("5 minutes ago", "yesterday", ...).
 *
 * The unit grows with the distance instead of showing everything in one fixed
 * unit - "203,844 minutes ago" is unreadable for anyone. Thresholds:
 *   < 1 minute   -> "just now" (numeric: 'auto')
 *   < 60 minutes -> minutes
 *   < 24 hours   -> hours
 *   < 30 days    -> days (numeric: 'auto' gives "yesterday")
 *   < 12 months  -> months
 *   otherwise    -> years
 *
 * @param value ISO timestamp (or Date/ms). Without a time zone, UTC is assumed,
 *              because the backend serialises naive UTC timestamps.
 * @param locale BCP-47 language, usually `i18n.language`
 */
export function formatRelativeTime(
  value: string | number | Date | null | undefined,
  locale?: string
): string | null {
  const date = parseTimestamp(value);
  if (date === null) return null;

  const diffMs = Date.now() - date.getTime();
  // Do not show the future (clock drift between box and browser) as "in 3 minutes".
  const elapsedMs = Math.max(0, diffMs);

  const rtf = new Intl.RelativeTimeFormat(locale || undefined, { numeric: 'auto' });

  const minutes = elapsedMs / 60_000;
  if (minutes < 1) return rtf.format(0, 'second');
  if (minutes < 60) return rtf.format(-Math.round(minutes), 'minute');

  const hours = minutes / 60;
  if (hours < 24) return rtf.format(-Math.round(hours), 'hour');

  const days = hours / 24;
  if (days < 30) {
    // By calendar days instead of elapsed hours: numeric 'auto' turns -1/-2
    // into "yesterday"/"the day before", and that has to match the date. 33
    // hours ago is "1 day" elapsed, but the day before yesterday by the calendar.
    return rtf.format(-calendarDaysBetween(date, new Date()), 'day');
  }

  const months = days / 30.44;
  if (months < 12) return rtf.format(-Math.round(months), 'month');

  return rtf.format(-Math.round(days / 365.25), 'year');
}

/**
 * Parse a backend timestamp. Timestamps without a zone suffix are read as
 * UTC - otherwise the local time zone shifts the result by hours.
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
 * Format a backend timestamp as an absolute local date/time - meant as a
 * tooltip for the relative value, when someone wants to see the exact date.
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
