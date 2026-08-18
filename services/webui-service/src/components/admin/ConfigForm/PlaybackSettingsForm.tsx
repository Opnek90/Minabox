import React, { useEffect, useState } from 'react';
import {
  Alert,
  Box,
  FormControlLabel,
  Switch,
  TextField,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import { useToast } from '@/contexts/ToastContext';
import { useFormState } from '@/hooks/useFormState';
import { configApi } from '@/api/config';
import type { GeneralConfig } from '@/types/api';
import { ActionButton } from '@/components/ui/ActionButton';
import { SettingsBlock } from '@/components/admin/SettingsBlock';

/**
 * Wiedergabe-Verhalten: was passiert beim Auflegen/Entfernen eines Tags und
 * welcher Sleep-Timer-Wert ist voreingestellt.
 *
 * Der frühere Einschlaf-Fade sitzt bewusst nicht mehr hier, sondern in
 * `ChildSettingsForm` – er ist eine Kinderschutz-Regel, keine Wiedergabe-Option.
 */
export const PlaybackSettingsForm: React.FC = () => {
  const { t } = useTranslation('admin');
  const { showSuccess } = useToast();
  const { saving, error, setError, run } = useFormState();
  const [general, setGeneral] = useState<GeneralConfig | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    configApi
      .getGeneral()
      .then((data) => {
        const g = data as GeneralConfig;
        setGeneral({
          ...g,
          stop_playback_on_tag_remove: g.stop_playback_on_tag_remove ?? false,
          resume_on_tag_rescan: g.resume_on_tag_rescan ?? true,
          sleep_timer_minutes: g.sleep_timer_minutes ?? 30,
        });
      })
      .catch(() => setError(t('load_error', { defaultValue: 'Laden fehlgeschlagen' })))
      .finally(() => setLoading(false));
  }, []);

  const handleSave = () =>
    run(async () => {
      if (!general) return;
      await configApi.updateGeneral({
        stop_playback_on_tag_remove: general.stop_playback_on_tag_remove,
        resume_on_tag_rescan: general.resume_on_tag_rescan,
        sleep_timer_minutes: general.sleep_timer_minutes,
      });
      setError(null);
      showSuccess(t('general.save_success'));
    });

  if (loading || !general) return null;

  return (
    <Box>
      <SettingsBlock
        title={t('control.section_rfid')}
        description={t('control.section_rfid_hint')}
      >
      <FormControlLabel
        control={
          <Switch
            checked={general.stop_playback_on_tag_remove ?? false}
            onChange={(e) =>
              setGeneral((p) =>
                p ? { ...p, stop_playback_on_tag_remove: e.target.checked } : p
              )
            }
          />
        }
        label={t('control.stop_playback_on_tag_remove')}
      />

      <FormControlLabel
        control={
          <Switch
            checked={general.resume_on_tag_rescan ?? true}
            onChange={(e) =>
              setGeneral((p) =>
                p ? { ...p, resume_on_tag_rescan: e.target.checked } : p
              )
            }
          />
        }
        label={t('control.resume_on_tag_rescan', {
          defaultValue: 'Ab letzter Position fortsetzen (Tag erneut auflegen)',
        })}
      />

      </SettingsBlock>

      <SettingsBlock title={t('general.sleep_timer')}>
      <TextField
        label={t('general.sleep_timer_minutes')}
        type="number"
        value={general.sleep_timer_minutes ?? 30}
        onChange={(e) =>
          setGeneral((p) =>
            p
              ? { ...p, sleep_timer_minutes: Math.max(1, parseInt(e.target.value, 10) || 30) }
              : p
          )
        }
        size="small"
        fullWidth
        inputProps={{ min: 1, max: 480 }}
        helperText={t('general.sleep_timer_minutes_hint')}
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
