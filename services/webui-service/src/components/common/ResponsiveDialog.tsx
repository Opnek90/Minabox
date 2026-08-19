import React from 'react';
import { Dialog, useTheme } from '@mui/material';
import type { DialogProps } from '@mui/material';
import { SAFE_AREA_BOTTOM } from '@/components/common/Navigation';
import { useLayout } from '@/hooks/useLayout';

/**
 * Dialog, der auf Telefonen als Vollbild-Sheet auftritt.
 *
 * Hintergrund: Ein zentrierter Dialog laesst auf einem 6–7"-Display bei
 * eingeblendeter Bildschirmtastatur nur noch ein paar hundert Pixel fuer das
 * Formular uebrig – der Speichern-Button in den `DialogActions` liegt dann
 * ausserhalb des sichtbaren Bereichs. Unterhalb des `sm`-Breakpoints nimmt der
 * Dialog deshalb den ganzen Schirm ein: Der Inhalt scrollt in `DialogContent`,
 * die Aktionsleiste bleibt am unteren Rand stehen.
 *
 * Bewusst nur fuer *Formular*-Dialoge gedacht. Ja/Nein-Bestaetigungen bleiben
 * kleine Karten – ein Vollbild-Sheet fuer eine Rueckfrage waere Overkill und
 * wuerde den Kontext dahinter unnoetig verdecken.
 *
 * Die API entspricht `Dialog`; ein explizit gesetztes `fullScreen` gewinnt.
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
          // Aktionsleiste ueber die Geraete-Schutzzone (Gestenleiste) heben.
          '& .MuiDialogActions-root': {
            paddingBottom: `calc(${theme.spacing(1)} + ${SAFE_AREA_BOTTOM})`,
          },
          // Scroll-Chaining unterbinden: Am Listenende soll nicht die Seite
          // hinter dem Sheet weiterscrollen.
          '& .MuiDialogContent-root': {
            overscrollBehavior: 'contain',
          },
        },
        ...(Array.isArray(sx) ? sx : [sx]),
      ]}
    />
  );
};
