import { clsx, type ClassValue } from 'clsx';

/**
 * Merges Tailwind class names safely.
 * Use this instead of plain string concatenation to avoid class conflicts.
 *
 * @example
 * cn('px-4 py-2', isActive && 'bg-[--color-accent]')
 */
export function cn(...inputs: ClassValue[]): string {
  return clsx(inputs);
}
