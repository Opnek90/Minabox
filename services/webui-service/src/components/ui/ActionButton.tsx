import * as React from 'react';
import { Button } from '@/components/ui/button';
import {
  useActionButtonStyles,
  type ActionType,
  type ColorOverride,
} from '@/hooks/useActionButtonStyles';
import { cn } from '@/lib/utils';

export type { ActionType, ColorOverride };

export interface ActionButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  /**
   * Semantic action type – drives variant, size and color automatically.
   *
   * - primary:     main call-to-action (Play, Save, Upload …)
   * - secondary:   supporting action (Cancel, Back …)
   * - icon:        icon-only compact button (Repeat, Refresh, Kiosk …)
   * - destructive: irreversible / dangerous action (Delete, Reset …)
   */
  actionType: ActionType;

  /** Optional icon rendered before the label */
  startIcon?: React.ReactNode;

  /** Optional icon rendered after the label */
  endIcon?: React.ReactNode;

  /**
   * Shows a loading spinner in place of startIcon and disables the button.
   * Useful for async mutations (save, upload, delete …).
   */
  loading?: boolean;

  /**
   * Override the accent color for special one-off cases.
   * The actionType semantics (variant, size, hover logic) still apply.
   */
  colorOverride?: ColorOverride;

  /** Additional Tailwind classes */
  className?: string;
}

/**
 * Minabox ActionButton
 *
 * The single button component to use across the entire WebUI.
 * Derive visual appearance solely from `actionType` + ThemeContext;
 * only use `colorOverride` for genuine edge cases.
 *
 * @example
 * // Primary action
 * <ActionButton actionType="primary" onClick={handleSave}>Save</ActionButton>
 *
 * // Icon-only
 * <ActionButton actionType="icon" aria-label="Refresh" onClick={refetch}>
 *   <RefreshIcon />
 * </ActionButton>
 *
 * // Destructive with loading state
 * <ActionButton actionType="destructive" loading={deleting} onClick={handleDelete}>
 *   Delete
 * </ActionButton>
 */
export const ActionButton = React.forwardRef<HTMLButtonElement, ActionButtonProps>(
  (
    {
      actionType,
      startIcon,
      endIcon,
      loading = false,
      colorOverride,
      className,
      children,
      disabled,
      ...props
    },
    ref,
  ) => {
    const { variant, size, className: styleClass } = useActionButtonStyles(
      actionType,
      colorOverride,
    );

    const isDisabled = disabled || loading;

    return (
      <Button
        ref={ref}
        variant={variant}
        size={size}
        disabled={isDisabled}
        className={cn(styleClass, className)}
        {...props}
      >
        {loading ? (
          <span
            className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent"
            aria-hidden="true"
          />
        ) : (
          startIcon
        )}
        {children}
        {endIcon}
      </Button>
    );
  },
);
ActionButton.displayName = 'ActionButton';
