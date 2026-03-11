import { useThemeContext } from '@/contexts/ThemeContext';
import type { ButtonProps as MuiButtonProps } from '@mui/material/Button';
import type { SxProps, Theme } from '@mui/material/styles';

export type ActionType = 'primary' | 'secondary' | 'icon' | 'destructive';

export interface ColorOverride {
  /** Main/background color (hex or CSS value) */
  main: string;
  /** Hover/dark shade */
  dark?: string;
  /** Foreground/text color */
  foreground?: string;
}

export interface ActionButtonStyles {
  muiVariant: MuiButtonProps['variant'];
  muiColor: MuiButtonProps['color'];
  sx: SxProps<Theme>;
}

/**
 * Maps an ActionType (+ optional ColorOverride) to concrete MUI Button props.
 *
 * Uses ThemeContext so active-state overrides (e.g. Repeat/Shuffle) always
 * reflect the current accent color.
 */
export function useActionButtonStyles(
  actionType: ActionType,
  colorOverride?: ColorOverride,
): ActionButtonStyles {
  const { mode } = useThemeContext();

  // Base MUI variant + color per actionType
  const variantMap: Record<ActionType, MuiButtonProps['variant']> = {
    primary:     'contained',
    secondary:   'outlined',
    icon:        'text',      // not used for MuiButton, only for reference
    destructive: 'contained',
  };

  const colorMap: Record<ActionType, MuiButtonProps['color']> = {
    primary:     'primary',
    secondary:   'primary',
    icon:        'primary',
    destructive: 'error',
  };

  const muiVariant = variantMap[actionType];
  const muiColor   = colorMap[actionType];

  // Build sx override when colorOverride is provided
  // (used e.g. for active Repeat/Shuffle icon buttons)
  let sx: SxProps<Theme> = {};

  if (colorOverride) {
    if (actionType === 'icon') {
      sx = {
        color: colorOverride.main,
        '&:hover': {
          backgroundColor: `${colorOverride.main}1a`, // ~10% opacity
        },
      };
    } else if (actionType === 'primary') {
      sx = {
        backgroundColor: colorOverride.main,
        color: colorOverride.foreground ?? '#ffffff',
        '&:hover': {
          backgroundColor: colorOverride.dark ?? colorOverride.main,
        },
      };
    } else if (actionType === 'secondary') {
      sx = {
        borderColor: colorOverride.main,
        color: colorOverride.main,
        '&:hover': {
          borderColor: colorOverride.dark ?? colorOverride.main,
          backgroundColor: `${colorOverride.main}1a`,
        },
      };
    }
  }

  // In dark mode, icon buttons get slightly more opacity on hover for contrast
  if (actionType === 'icon' && mode === 'dark' && !colorOverride) {
    sx = { ...sx, '&:hover': { backgroundColor: 'rgba(255,255,255,0.08)' } };
  }

  return { muiVariant, muiColor, sx };
}
