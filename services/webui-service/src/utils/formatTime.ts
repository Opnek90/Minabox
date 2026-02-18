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
