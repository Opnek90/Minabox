import React, { useEffect, useState } from 'react';
import { Alert, Box, TextField } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { useToast } from '@/contexts/ToastContext';
import { useFormState } from '@/hooks/useFormState';
import { configApi } from '@/api/config';
import type { GeneralConfig } from '@/types/api';
import { ActionButton } from '@/components/ui/ActionButton';
import { SettingsBlock } from '@/components/admin/SettingsBlock';

const DEFAULT_DOMAINS = ['soundcloud.com', 'www.soundcloud.com', 'bandcamp.com'];

/**
 * Hosts a "download from URL" import may be used against.
 *
 * A technical guard against arbitrary fetch targets, not a legal clearance of
 * the content hosted there - see the lawful-use notice shown before an
 * import. YouTube is deliberately not in the shipped default: unlike
 * SoundCloud and Bandcamp, it has no built-in download feature a rights
 * holder opts into, which makes importing from it a meaningfully bigger
 * legal question. Add it here only once you are sure that question is
 * answered for your use case. Takes effect immediately, no restart needed.
 */
export const MediaImportDomainsForm: React.FC = () => {
  const { t } = useTranslation('admin');
  const { showSuccess } = useToast();
  const { saving, error, setError, run } = useFormState();
  const [domainsText, setDomainsText] = useState<string | null>(null);

  useEffect(() => {
    configApi
      .getGeneral()
      .then((data) =>
        setDomainsText(
          ((data as GeneralConfig).media_import_allowed_domains ?? DEFAULT_DOMAINS).join(', '),
        ),
      )
      .catch(() => setError(t('load_error')));
  }, []);

  const handleSave = () =>
    run(async () => {
      if (domainsText === null) return;
      const domains = domainsText
        .split(',')
        .map((d) => d.trim().toLowerCase())
        .filter(Boolean);
      await configApi.updateGeneral({ media_import_allowed_domains: domains });
      setError(null);
      showSuccess(t('general.save_success'));
    });

  if (domainsText === null) return null;

  return (
    <Box>
      <SettingsBlock title={t('general.media_import_domains_title')}>
        <TextField
          label={t('general.media_import_domains_label')}
          value={domainsText}
          onChange={(e) => setDomainsText(e.target.value)}
          placeholder="soundcloud.com, bandcamp.com"
          size="small"
          fullWidth
          multiline
          minRows={2}
          helperText={t('general.media_import_domains_hint')}
        />
      </SettingsBlock>

      {error && <Alert severity="error">{error}</Alert>}
      <Box>
        <ActionButton actionType="primary" onClick={handleSave} disabled={saving}>
          {t('save', { ns: 'common' })}
        </ActionButton>
      </Box>
    </Box>
  );
};
