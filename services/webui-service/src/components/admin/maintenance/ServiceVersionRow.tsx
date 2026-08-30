import React from 'react';
import { Box, Chip, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import type { ServiceUpdateInfo } from '@/api/system';

/** Eine Zeile der Versionsliste: Dienst, laufende Version, Hinweis auf Neues. */
export const ServiceVersionRow: React.FC<{ service: ServiceUpdateInfo }> = ({ service }) => {
  const { t } = useTranslation('admin');
  return (
    <Box display="flex" alignItems="baseline" gap={1} sx={{ minWidth: 0 }}>
      <Typography variant="body2" sx={{ textTransform: 'capitalize', flex: 1, minWidth: 0 }} noWrap>
        {service.service}
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ fontVariantNumeric: 'tabular-nums' }}>
        {service.installed}
      </Typography>
      {service.update_available && service.latest && (
        <Chip size="small" color="primary" label={`→ ${service.latest}`} />
      )}
      {service.pending_publish && (
        // Das Manifest ist der Registry voraus - anbieten waere ein Versprechen,
        // das der Pull nicht halten koennte.
        <Chip size="small" variant="outlined" label={t('system.pending_publish')} />
      )}
    </Box>
  );
};
