import React, { useEffect, useState } from 'react';
import { Alert, Box, InputAdornment, TextField } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { useGeneralConfigField } from '@/hooks/useGeneralConfig';
import { ActionButton } from '@/components/ui/ActionButton';
import { SettingsBlock } from '@/components/admin/SettingsBlock';
import { HelpTip } from '@/components/ui/HelpTip';

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
  const { value: domains, setValue, save, saving, error } = useGeneralConfigField(
    'media_import_allowed_domains',
    DEFAULT_DOMAINS,
  );

  // The only settings field that is edited in a different shape than it is
  // stored: a comma-separated line here, a list on disk. Re-parsing on every
  // keystroke would swallow the separator while it is being typed, so the text
  // is its own state and only the parsed list goes back to the hook.
  const [text, setText] = useState<string | null>(null);

  useEffect(() => {
    if (domains !== null && text === null) setText(domains.join(', '));
  }, [domains, text]);

  const handleChange = (next: string) => {
    setText(next);
    setValue(
      next
        .split(',')
        .map((d) => d.trim().toLowerCase())
        .filter(Boolean),
    );
  };

  if (text === null) return null;

  return (
    <Box>
      <SettingsBlock title={t('general.media_import_domains_title')}>
        <TextField
          label={t('general.media_import_domains_label')}
          value={text}
          onChange={(e) => handleChange(e.target.value)}
          placeholder="soundcloud.com, bandcamp.com"
          size="small"
          fullWidth
          multiline
          minRows={2}
          InputProps={{
            endAdornment: (
              // Bei mehrzeiligem Feld sonst mittig zwischen den Zeilen.
              <InputAdornment position="end" sx={{ alignSelf: 'flex-start', mt: 1.25 }}>
                <HelpTip
                  title={t('general.media_import_domains_hint')}
                  label={t('general.media_import_domains_label')}
                />
              </InputAdornment>
            ),
          }}
        />
      </SettingsBlock>

      {error && <Alert severity="error">{error}</Alert>}
      <Box>
        <ActionButton actionType="primary" onClick={save} disabled={saving}>
          {t('save', { ns: 'common' })}
        </ActionButton>
      </Box>
    </Box>
  );
};
