import React from 'react';
import {
  Alert,
  Box,
  Collapse,
  FormControlLabel,
  InputAdornment,
  Switch,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import { useGeneralConfigFields } from '@/hooks/useGeneralConfig';
import { ActionButton } from '@/components/ui/ActionButton';
import { SettingsBlock } from '@/components/admin/SettingsBlock';
import { VolumeSlider } from '@/components/ui/VolumeSlider';
import { HelpTip } from '@/components/ui/HelpTip';

/**
 * Spoken announcements - what the box says out loud, and how loudly.
 *
 * The section only appears with the optional "voice" component installed
 * (`requiresFeature` in `settingsIndex`), so nothing here has to explain that
 * a box without it stays silent.
 *
 * The four switches are deliberately not one per sentence: a parent decides
 * "tell them about cards the box does not know", not one wording at a time.
 * Which phrase hangs off which switch is decided in the backend
 * (`core/announcements.py`).
 */

const LANGUAGES = ['de', 'en'] as const;

const LANGUAGE_LABEL_KEY = {
  de: 'announce.language_de',
  en: 'announce.language_en',
} as const satisfies Record<(typeof LANGUAGES)[number], string>;

const DEFAULT_WARNING_MINUTES = 10;

export const AnnouncementSettingsForm: React.FC = () => {
  const { t } = useTranslation('admin');
  const { values, setValue, save, saving, error } = useGeneralConfigFields({
    announcements_enabled: false,
    announce_card_name: true,
    announce_unknown_card: true,
    announce_usage_limit: true,
    announce_mute: true,
    announce_language: 'de' as const,
    announce_volume_percent: 90,
    announce_duck_percent: 30,
    announce_limit_warning_minutes: DEFAULT_WARNING_MINUTES,
  });

  if (!values) return null;

  const on = values.announcements_enabled;

  return (
    <Box>
      <SettingsBlock title={t('announce.title')} help={t('announce.hint')}>
        <FormControlLabel
          control={
            <Switch
              checked={on}
              onChange={(e) => setValue('announcements_enabled', e.target.checked)}
            />
          }
          label={t('announce.enabled')}
        />
      </SettingsBlock>

      {/* Everything below is meaningless with the box silent, and a page full
          of dead controls reads as broken rather than as switched off. */}
      <Collapse in={on} unmountOnExit>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
          <SettingsBlock title={t('announce.what_title')} help={t('announce.what_hint')}>
            <FormControlLabel
              control={
                <Switch
                  checked={values.announce_card_name}
                  onChange={(e) => setValue('announce_card_name', e.target.checked)}
                />
              }
              label={t('announce.card_name')}
            />
            <FormControlLabel
              control={
                <Switch
                  checked={values.announce_unknown_card}
                  onChange={(e) => setValue('announce_unknown_card', e.target.checked)}
                />
              }
              label={t('announce.unknown_card')}
            />
            <FormControlLabel
              control={
                <Switch
                  checked={values.announce_usage_limit}
                  onChange={(e) => setValue('announce_usage_limit', e.target.checked)}
                />
              }
              label={t('announce.usage_limit')}
            />
            <FormControlLabel
              control={
                <Switch
                  checked={values.announce_mute}
                  onChange={(e) => setValue('announce_mute', e.target.checked)}
                />
              }
              label={t('announce.mute')}
            />

            <Collapse in={values.announce_usage_limit} unmountOnExit>
              <TextField
                label={t('announce.warning_minutes')}
                type="number"
                value={values.announce_limit_warning_minutes}
                onChange={(e) => {
                  const parsed = parseInt(e.target.value, 10);
                  setValue(
                    'announce_limit_warning_minutes',
                    Math.max(0, Math.min(60, Number.isNaN(parsed) ? DEFAULT_WARNING_MINUTES : parsed)),
                  );
                }}
                size="small"
                fullWidth
                inputProps={{ min: 0, max: 60 }}
                InputProps={{
                  endAdornment: (
                    <InputAdornment position="end">
                      <HelpTip
                        title={t('announce.warning_minutes_hint')}
                        label={t('announce.warning_minutes')}
                      />
                    </InputAdornment>
                  ),
                }}
              />
            </Collapse>
          </SettingsBlock>

          <SettingsBlock title={t('announce.voice_title')}>
            <ToggleButtonGroup
              exclusive
              fullWidth
              value={values.announce_language}
              onChange={(_, v: (typeof LANGUAGES)[number] | null) => {
                if (!v) return;
                setValue('announce_language', v);
              }}
            >
              {LANGUAGES.map((code) => (
                <ToggleButton key={code} value={code}>
                  {t(LANGUAGE_LABEL_KEY[code])}
                </ToggleButton>
              ))}
            </ToggleButtonGroup>

            <VolumeSlider
              label={t('announce.volume')}
              value={values.announce_volume_percent}
              onChange={(v) => setValue('announce_volume_percent', v)}
            />

            <VolumeSlider
              label={t('announce.duck')}
              value={values.announce_duck_percent}
              onChange={(v) => setValue('announce_duck_percent', v)}
            />
          </SettingsBlock>
        </Box>
      </Collapse>

      {error && <Alert severity="error">{error}</Alert>}
      <Box>
        <ActionButton actionType="primary" onClick={save} disabled={saving}>
          {t('save', { ns: 'common' })}
        </ActionButton>
      </Box>
    </Box>
  );
};
