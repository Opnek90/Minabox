import React from 'react';
import { Box, Divider, Typography } from '@mui/material';

interface SettingsSectionProps {
  title: string;
  /** Kurze Erklaerung unter dem Titel - wie bei `SettingsBlock`, eine Ebene hoeher. */
  description?: string;
  children: React.ReactNode;
}

/**
 * Zweite Ebene der Einstellungsseite: eine Section innerhalb einer Gruppe.
 * Die Bloecke darin rendert `SettingsBlock`.
 *
 * Die Breitenbegrenzung sitzt bewusst hier statt in den Formularen: vorher
 * begrenzten nur 6 von 21 Panels auf 560px, der Rest lief ueber die volle
 * Breite – auf dem Desktop stand dadurch ein schmales Formular direkt neben
 * einem randlosen Panel.
 */
export const SettingsSection: React.FC<SettingsSectionProps> = ({
  title,
  description,
  children,
}) => (
  <Box sx={{ mb: 4, maxWidth: 720 }}>
    <Typography variant="subtitle1" fontWeight={600} gutterBottom={!description}>
      {title}
    </Typography>
    {description && (
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
        {description}
      </Typography>
    )}
    <Divider sx={{ mb: 2.5 }} />
    {children}
  </Box>
);
