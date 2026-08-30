/**
 * Validate a URL string
 */
export function isValidUrl(url: string): boolean {
  try {
    new URL(url);
    return true;
  } catch {
    return false;
  }
}

/**
 * Validate that a string is not empty
 */
export function isNotEmpty(value: string): boolean {
  return value.trim().length > 0;
}

/**
 * Validate a volume value (0-100)
 */
export function isValidVolume(value: number): boolean {
  return Number.isInteger(value) && value >= 0 && value <= 100;
}

/**
 * Validate a GPIO pin number
 */
export function isValidGpio(value: number): boolean {
  return Number.isInteger(value) && value >= 0 && value <= 40;
}

/**
 * Minimum length of the WebUI password.
 *
 * This is the only lock in front of the media library, the parent dashboard
 * and maintenance - and maintenance holds the factory reset, the OS update and
 * the backup download with the whole database. The system password the
 * Host-Helper sets asks for eight characters, so this matches it.
 *
 * The backend enforces the same value in routes_auth.py; changing it here
 * alone only moves the cosmetics.
 */
export const MIN_PASSWORD_LENGTH = 8;
