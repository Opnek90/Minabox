import React from 'react';
import { Box, Typography } from '@mui/material';

interface SettingsBlockProps {
  title: string;
  /** Kurze Erklaerung unter dem Titel – ganze Saetze gehoeren hierhin, nicht in den Titel. */
  description?: string;
  children: React.ReactNode;
}

/**
 * Dritte Ebene der Einstellungsseite: ein thematischer Block *innerhalb* einer
 * `SettingsSection`.
 *
 * Vorher erfand jedes Formular diese Ebene neu – im Bestand fanden sich vier
 * Varianten nebeneinander (`overline` mit und ohne `text.secondary`,
 * `subtitle1` fett in einem Paper, `subtitle2` secondary), teils zwei davon in
 * derselben Datei. Erklaertexte hingen mal als `caption` unter dem Titel, mal
 * als `body2` unter dem Feld.
 *
 * Regeln, die diese Komponente durchsetzt:
 * - Jeder Block hat einen Titel – auch der erste einer Section. Vorher standen
 *   die ersten Felder einer Section regelmaessig ueberschriftslos da und man
 *   musste raten, wozu sie gehoeren.
 * - Ein Erklaertext steht direkt unter dem Titel, nie unter dem Feld.
 * - Der Titel wiederholt nicht den Namen seiner Gruppe oder Section.
 */
export const SettingsBlock: React.FC<SettingsBlockProps> = ({
  title,
  description,
  children,
}) => (
  <Box sx={{ mb: 3 }}>
    <Typography
      variant="overline"
      color="text.secondary"
      sx={{ display: 'block', lineHeight: 1.6 }}
    >
      {title}
    </Typography>
    {description && (
      <Typography
        variant="caption"
        color="text.secondary"
        sx={{ display: 'block', mb: 0.5 }}
      >
        {description}
      </Typography>
    )}
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, mt: 1 }}>
      {children}
    </Box>
  </Box>
);
