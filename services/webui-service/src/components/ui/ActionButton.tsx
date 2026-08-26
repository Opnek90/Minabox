import * as React from 'react';
import MuiButton, { type ButtonProps as MuiButtonProps } from '@mui/material/Button';
import MuiIconButton from '@mui/material/IconButton';
import CircularProgress from '@mui/material/CircularProgress';
import type { SxProps, Theme } from '@mui/material/styles';
import {
  useActionButtonStyles,
  type ActionType,
  type ColorOverride,
} from '@/hooks/useActionButtonStyles';

export type { ActionType, ColorOverride };

// `color` is dropped from the HTML attributes and re-declared below: the DOM
// one is a plain string, MUI's is a union, and a call site that means the MUI
// palette should be told when it typos the name.
export interface ActionButtonProps
  extends Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, 'color'> {
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
  /**
   * Layout tweaks from the call site - width, margins, flex behaviour.
   *
   * Merged *on top of* the styling that `actionType` produces, never in place
   * of it. Passing sx used to replace it wholesale, which silently cost those
   * buttons their height, padding and font weight.
   */
  sx?: SxProps<Theme>;
  fullWidth?: boolean;
  /**
   * Palette override. `actionType` is what decides how a button looks, but an
   * outlined button can still want to be red - "delete logo" is secondary in
   * weight and destructive in meaning at the same time.
   */
  color?: MuiButtonProps['color'];
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
      sx: sxFromCaller,
      fullWidth,
      color,
      ...rest
    },
    ref,
  ) => {
    const { muiVariant, muiColor, sx: sxFromType } = useActionButtonStyles(
      actionType,
      colorOverride,
    );

    const isDisabled = disabled || loading;

    // Appended, not substituted. MUI resolves an sx array left to right, so
    // the call site still wins on the properties it names while everything
    // actionType set survives.
    const sx: SxProps<Theme> = [sxFromType, sxFromCaller] as SxProps<Theme>;

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
          {...rest}
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
        color={color ?? muiColor}
        size={size}
        fullWidth={fullWidth}
        disabled={isDisabled}
        onClick={onClick as React.MouseEventHandler<HTMLButtonElement>}
        aria-label={ariaLabel}
        className={className}
        startIcon={loading ? <CircularProgress size={14} color="inherit" /> : startIcon}
        endIcon={endIcon}
        sx={sx}
        {...rest}
      >
        {children}
      </MuiButton>
    );
  },
);
ActionButton.displayName = 'ActionButton';
