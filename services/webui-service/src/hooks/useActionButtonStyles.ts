import { useThemeContext } from '@/contexts/ThemeContext';
import type { ButtonVariant, ButtonSize } from '@/components/ui/button';
import { cn } from '@/lib/utils';

export type ActionType = 'primary' | 'secondary' | 'icon' | 'destructive';

export interface ColorOverride {
  /** Override the main/background color (hex or CSS value) */
  main: string;
  /** Override the hover/dark shade */
  dark?: string;
  /** Override the foreground/text color */
  foreground?: string;
}

export interface ActionButtonStyles {
  variant: ButtonVariant;
  size: ButtonSize;
  /** Additional Tailwind classes derived from context + override */
  className: string;
}

/**
 * Maps an ActionType (+ optional ColorOverride) to the concrete
 * shadcn Button variant, size and Tailwind class string.
 *
 * Reads ThemeContext so returned styles always reflect the currently
 * active accent color and light/dark mode.
 *
 * @example
 * const { variant, size, className } = useActionButtonStyles('primary');
 * <Button variant={variant} size={size} className={className} />
 */
export function useActionButtonStyles(
  actionType: ActionType,
  colorOverride?: ColorOverride,
): ActionButtonStyles {
  const { mode } = useThemeContext();

  const variantMap: Record<ActionType, ButtonVariant> = {
    primary:     'default',
    secondary:   'outline',
    icon:        'ghost',
    destructive: 'destructive',
  };

  const sizeMap: Record<ActionType, ButtonSize> = {
    primary:     'default',
    secondary:   'default',
    icon:        'icon',
    destructive: 'default',
  };

  const variant = variantMap[actionType];
  const size    = sizeMap[actionType];

  // Build override classes when colorOverride is provided.
  // We use inline CSS vars scoped to the element via style, but for
  // className we only add dark-mode-aware utility tweaks here.
  const overrideClasses = colorOverride
    ? cn(
        // Replace accent with override main color via arbitrary value
        actionType === 'primary'   && `bg-[${colorOverride.main}] hover:bg-[${colorOverride.dark ?? colorOverride.main}]`,
        actionType === 'secondary' && `border-[${colorOverride.main}] text-[${colorOverride.main}]`,
        actionType === 'icon'      && `text-[${colorOverride.main}] hover:bg-[${colorOverride.main}]/10`,
        colorOverride.foreground   && `text-[${colorOverride.foreground}]`,
      )
    : '';

  // Dark mode: icon buttons get slightly lighter text for contrast
  const modeClasses = cn(
    actionType === 'icon' && mode === 'dark' && 'text-[--color-accent-light]',
  );

  return {
    variant,
    size,
    className: cn(overrideClasses, modeClasses),
  };
}
