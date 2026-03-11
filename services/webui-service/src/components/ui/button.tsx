import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

/**
 * Shadcn-style Button primitive powered by CVA.
 *
 * Variants map directly to the Minabox ActionType convention:
 *   default     → primary action
 *   outline     → secondary action
 *   ghost       → icon / subtle action
 *   destructive → dangerous / irreversible action
 *
 * Colors are driven by CSS custom properties defined in index.css and
 * updated at runtime by ThemeContext (accent color + dark/light mode).
 */
const buttonVariants = cva(
  // Base styles shared by all variants
  [
    'inline-flex items-center justify-center gap-2 whitespace-nowrap',
    'rounded-md font-medium transition-colors duration-150',
    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2',
    'focus-visible:ring-[--color-accent]',
    'disabled:pointer-events-none disabled:opacity-50',
    'select-none',
  ],
  {
    variants: {
      variant: {
        /** Primary: filled with accent color */
        default:
          'bg-[--color-accent] text-[--color-accent-contrast] hover:bg-[--color-accent-dark] focus-visible:ring-[--color-accent]',
        /** Secondary: outlined with accent color */
        outline:
          'border border-[--color-accent] text-[--color-accent] bg-transparent hover:bg-[--color-accent]/10',
        /** Ghost / Icon: transparent background, subtle hover */
        ghost:
          'bg-transparent text-[--color-accent] hover:bg-[--color-accent]/10 focus-visible:ring-[--color-accent]',
        /** Destructive: fixed red palette, not accent-dependent */
        destructive:
          'bg-[--color-destructive] text-[--color-destructive-contrast] hover:bg-[--color-destructive-dark] focus-visible:ring-[--color-destructive]',
      },
      size: {
        default: 'h-10 px-4 py-2 text-sm',
        sm:      'h-8  px-3 py-1 text-xs',
        lg:      'h-12 px-6 py-3 text-base',
        /** Icon: square, no padding text – use with a single icon child */
        icon:    'h-9 w-9 p-0',
      },
    },
    defaultVariants: {
      variant: 'default',
      size:    'default',
    },
  },
);

export type ButtonVariant = 'default' | 'outline' | 'ghost' | 'destructive';
export type ButtonSize    = 'default' | 'sm' | 'lg' | 'icon';

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  /** Render as child element (Radix asChild pattern) */
  asChild?: boolean;
}

/**
 * Base Button component.
 * Prefer using ActionButton with actionType instead of this directly.
 */
export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild: _asChild, ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={cn(buttonVariants({ variant, size }), className)}
        {...props}
      />
    );
  },
);
Button.displayName = 'Button';

export { buttonVariants };
