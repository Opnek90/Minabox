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
