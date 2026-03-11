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
 *
 * Visual language: rounded-lg corners, font-semibold, consistent height,
 * matches the existing "Playlist hinzufügen" button style.
 */
const buttonVariants = cva(
  [
    'inline-flex items-center justify-center gap-1.5 whitespace-nowrap',
    'font-semibold transition-colors duration-150',
    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2',
    'focus-visible:ring-[--color-accent]',
    'disabled:pointer-events-none disabled:opacity-50',
    'cursor-pointer select-none',
  ],
  {
    variants: {
      variant: {
        /** Primary: filled accent – matches existing "Playlist hinzufügen" look */
        default:
          'rounded-lg bg-[--color-accent] text-[--color-accent-contrast] hover:bg-[--color-accent-dark]',

        /** Secondary: subtle outline, slight tinted background */
        outline:
          'rounded-lg border border-[--color-accent] text-[--color-accent] bg-[--color-surface]/5 hover:bg-[--color-accent]/15',

        /** Ghost / Icon: circular, transparent – for icon-only buttons */
        ghost:
          'rounded-full bg-transparent text-[--color-accent] hover:bg-[--color-accent]/15',

        /** Destructive: fixed red palette */
        destructive:
          'rounded-lg bg-[--color-destructive] text-[--color-destructive-contrast] hover:bg-[--color-destructive-dark] focus-visible:ring-[--color-destructive]',
      },
      size: {
        /** Default: matches height of existing action buttons in PageShell */
        default: 'h-9 px-4 py-2 text-sm',
        sm:      'h-9 px-4 py-2 text-sm',
        lg:      'h-11 px-6 py-2.5 text-base',
        /** Icon: circular, tight – pairs with ghost variant */
        icon:    'h-8 w-8 p-0',
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
