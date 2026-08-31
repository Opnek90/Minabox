import React from 'react';
import { Box, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import type { ServiceUpdateInfo } from '@/api/system';

/** Release notes of a version in the configured language. */
export const ReleaseNotesList: React.FC<{ service: ServiceUpdateInfo }> = ({ service }) => {
  const { t, i18n } = useTranslation('admin');
  // Deutsch als Rueckfall: die Notizen entstehen zuerst auf Deutsch, eine
  // fehlende Uebersetzung soll keine leere Liste ergeben.
  const lang = i18n.language.startsWith('en') ? 'en' : 'de';
  const categories: Array<['added' | 'improved' | 'fixed', string]> = [
    ['added', t('system.notes_added')],
    ['improved', t('system.notes_improved')],
    ['fixed', t('system.notes_fixed')],
  ];

  return (
    <Box sx={{ mb: 2 }}>
      <Typography variant="subtitle2" sx={{ textTransform: 'capitalize' }}>
        {service.service} {service.installed} → {service.latest}
      </Typography>
      {service.releases.length === 0 && (
        <Typography variant="body2" color="text.secondary">
          {t('system.no_notes')}
        </Typography>
      )}
      {service.releases.map((release) => (
        <Box key={release.version} sx={{ mt: 1 }}>
          <Typography variant="caption" color="text.secondary">
            {release.version}
            {release.date ? ` · ${new Date(release.date).toLocaleDateString()}` : ''}
          </Typography>
          {categories.map(([key, label]) => {
            const items = release.notes?.[key]?.[lang] ?? release.notes?.[key]?.de ?? [];
            if (items.length === 0) return null;
            return (
              <Box key={key} sx={{ mt: 0.5 }}>
                <Typography variant="caption" fontWeight={600}>{label}</Typography>
                <Box component="ul" sx={{ m: 0, pl: 2.5 }}>
                  {items.map((item, index) => (
                    <Typography component="li" variant="body2" key={index}>{item}</Typography>
                  ))}
                </Box>
              </Box>
            );
          })}
        </Box>
      ))}
    </Box>
  );
};
