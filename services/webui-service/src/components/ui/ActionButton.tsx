import * as React from 'react';
import MuiButton, { type ButtonProps as MuiButtonProps } from '@mui/material/Button';
import MuiIconButton from '@mui/material/IconButton';
import CircularProgress from '@mui/material/CircularProgress';
import {
  useActionButtonStyles,
  type ActionType,
  type ColorOverride,
} from '@/hooks/useActionButtonStyles';

export type { ActionType, ColorOverride };

export interface ActionButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  /**
   * Semantic action type – drives MUI variant + color automatically.
   *
   * - primary:     main CTA – MUI contained primary
   * - secondary:   supporting action – MUI outlined primary
   * - icon:        icon-only – MUI IconButton
   * - destructive: irreversible action – MUI contained error
   */
  actionType: ActionType;
  startIcon?: React.ReactNode;
  endIcon?: React.ReactNode;
  /** Visual size of the button – maps to MUI Button/IconButton size (default: small) */
  size?: MuiButtonProps['size'];
  /** Shows a spinner and disables the button during async operations */
  loading?: boolean;
  /** One-off color override (e.g. active-state for Repeat/Shuffle) */
  colorOverride?: ColorOverride;
  className?: string;
  disabled?: boolean;
  children?: React.ReactNode;
  'aria-label'?: string;
}

/**
 * Minabox ActionButton – MUI-backed, themed via ThemeContext.
 *
 * Single button component for the entire WebUI.
 * Visual appearance is derived solely from `actionType`.
 */
export const ActionButton = React.forwardRef<HTMLButtonElement, ActionButtonProps>(
  (
    {
      actionType,
      startIcon,
      endIcon,
      size = 'small',
      loading = false,
      colorOverride,
      className,
      children,
      disabled,
      onClick,
      'aria-label': ariaLabel,
      ...rest
    },
    ref,
  ) => {
    const { muiVariant, muiColor, sx } = useActionButtonStyles(actionType, colorOverride);

    const isDisabled = disabled || loading;

    // Icon-only button
    if (actionType === 'icon') {
      return (
        <MuiIconButton
          ref={ref as React.Ref<HTMLButtonElement>}
          size={size}
          disabled={isDisabled}
          onClick={onClick as React.MouseEventHandler<HTMLButtonElement>}
          aria-label={ariaLabel}
          className={className}
          sx={sx}
        >
          {loading
            ? <CircularProgress size={16} color="inherit" />
            : children
          }
        </MuiIconButton>
      );
    }

    // Text / contained / outlined button
    return (
      <MuiButton
        ref={ref as React.Ref<HTMLButtonElement>}
        variant={muiVariant}
        color={muiColor}
        size={size}
        disabled={isDisabled}
        onClick={onClick as React.MouseEventHandler<HTMLButtonElement>}
        aria-label={ariaLabel}
        className={className}
        startIcon={loading ? <CircularProgress size={14} color="inherit" /> : startIcon}
        endIcon={endIcon}
        sx={sx}
        {...(rest as any)}
      >
        {children}
      </MuiButton>
    );
  },
);
ActionButton.displayName = 'ActionButton';
