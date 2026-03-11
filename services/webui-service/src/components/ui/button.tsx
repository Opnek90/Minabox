import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

/**
 * Shadcn-style Button primitive powered by CVA.
 *
 * Variants map directly to the Minabox ActionType convention:
 *   default     → primary action   (filled accent, pill)
 *   outline     → secondary action  (soft tinted fill, no border, pill)
 *   ghost       → icon / subtle     (transparent, circular)
 *   destructive → dangerous action  (filled red, pill)
 *
 * Visual language: pill shape (rounded-full), no outlines on text buttons,
 * consistent with the existing orange "Playlist hinzufügen" button.
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
        /**
         * Primary: fully filled with accent color.
         * Identical to existing "Playlist hinzufügen" button.
         */
        default:
          'rounded-full bg-[--color-accent] text-[--color-accent-contrast] hover:bg-[--color-accent-dark]',

        /**
         * Secondary: soft tinted fill, NO border.
         * Reads as secondary without looking dated/boxed.
         */
        outline:
          'rounded-full bg-[--color-accent]/20 text-[--color-accent] hover:bg-[--color-accent]/30',

        /**
         * Ghost / Icon: circular transparent button for icon-only use.
         */
        ghost:
          'rounded-full bg-transparent text-[--color-accent] hover:bg-[--color-accent]/15',

        /**
         * Destructive: filled red pill for delete / irreversible actions.
         */
        destructive:
          'rounded-full bg-[--color-destructive] text-[--color-destructive-contrast] hover:bg-[--color-destructive-dark] focus-visible:ring-[--color-destructive]',
      },
      size: {
        default: 'h-9 px-5 py-2 text-sm',
        sm:      'h-9 px-5 py-2 text-sm',
        lg:      'h-11 px-7 py-2.5 text-base',
        /** Icon: fixed square – use with ghost variant */
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
