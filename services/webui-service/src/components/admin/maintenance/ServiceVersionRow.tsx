import React from 'react';
import { Box, Chip, Tooltip, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import type { ServiceUpdateInfo } from '@/api/system';

/** One row of the version list: service, running version, hint of something new. */
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
      {/* Not the channel the box follows but the one this build came from:
          after switching back to stable, a running candidate stays visible as
          one until it is replaced. "beta" is the same word in both languages. */}
      {service.channel === 'beta' && (
        <Chip size="small" color="warning" variant="outlined" label="beta" />
      )}
      {service.update_available && service.latest && (
        <Chip size="small" color="primary" label={`→ ${service.latest}`} />
      )}
      {service.pending_publish && (
        // The manifest is ahead of the registry - offering it would be a
        // promise the pull could not keep.
        <Chip size="small" variant="outlined" label={t('system.pending_publish')} />
      )}
      {service.requires_unmet?.length ? (
        // Held back because the box would end up on a combination nobody
        // built. Shown rather than hidden, and with the missing version in
        // the tooltip: "why is there nothing for this one" is the question
        // that gets asked either way.
        <Tooltip
          title={t('system.requires_unmet_hint', {
            service: service.requires_unmet[0].service,
            version: service.requires_unmet[0].minimum,
          })}
        >
          <Chip
            size="small"
            color="warning"
            variant="outlined"
            label={t('system.requires_unmet', { service: service.requires_unmet[0].service })}
          />
        </Tooltip>
      ) : null}
    </Box>
  );
};
