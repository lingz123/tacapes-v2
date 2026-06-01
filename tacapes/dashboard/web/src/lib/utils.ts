import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

/**
 * Standard shadcn helper. Joins class names and lets later Tailwind utilities
 * win conflicts with earlier ones — so `cn('p-2', condition && 'p-4')` resolves
 * cleanly to `p-4` instead of producing both classes.
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
