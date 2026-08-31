import React from 'react';
import { Dialog, useTheme } from '@mui/material';
import type { DialogProps } from '@mui/material';
import { SAFE_AREA_BOTTOM } from '@/components/common/Navigation';
import { useLayout } from '@/hooks/useLayout';

/**
 * A dialog that appears as a full-screen sheet on phones.
 *
 * Background: on a 6-7" display with the on-screen keyboard up, a centred
 * dialog leaves only a few hundred pixels for the form - the save button in
 * `DialogActions` is then outside the visible area. Below the `sm` breakpoint
 * the dialog therefore takes the whole screen: the content scrolls in
 * `DialogContent`, the action bar stays at the bottom edge.
 *
 * Deliberately meant only for *form* dialogs. Yes/no confirmations stay small
 * cards - a full-screen sheet for a follow-up question would be overkill and
 * would needlessly hide the context behind it.
 *
 * The API matches `Dialog`; an explicitly set `fullScreen` wins.
 */
export const ResponsiveDialog: React.FC<DialogProps> = ({ sx, ...props }) => {
  const theme = useTheme();
  const fullScreen = useLayout().isMobile;

  return (
    <Dialog
      fullScreen={fullScreen}
      {...props}
      sx={[
        fullScreen && {
          // Lift the action bar above the device safe area (gesture bar).
          '& .MuiDialogActions-root': {
            paddingBottom: `calc(${theme.spacing(1)} + ${SAFE_AREA_BOTTOM})`,
          },
          // Prevent scroll chaining: at the end of the list, the page behind
          // the sheet must not keep scrolling.
          '& .MuiDialogContent-root': {
            overscrollBehavior: 'contain',
          },
        },
        ...(Array.isArray(sx) ? sx : [sx]),
      ]}
    />
  );
};
