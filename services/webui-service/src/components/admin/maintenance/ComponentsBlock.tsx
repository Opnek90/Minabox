import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Box,
  Chip,
  FormControlLabel,
  Switch,
  Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import {
  componentsApi,
  PROFILE_FEATURE,
  type ComponentEntry,
  type ComponentProfile,
} from '@/api/components';
import { useCapabilities } from '@/contexts/CapabilitiesContext';
import { ActionButton } from '@/components/ui/ActionButton';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { SettingsBlock } from '@/components/admin/SettingsBlock';
import { HelpLabel } from '@/components/ui/HelpTip';
import { UpdateProgressDialog } from './UpdateProgressDialog';
import { useComponentsRun } from './useComponentsRun';

/**
 * Adding and removing card reader, LEDs, buttons, display and media import.
 *
 * This was the last setup step that still needed an SSH session and the
 * maintenance menu of `install.sh` (#180). The switches are a *wish*, not a
 * live toggle: nothing happens until "apply", because one press means removing
 * and recreating containers, and the box restarts services over it.
 *
 * Switching a component off deletes nothing. Its card assignments and settings
 * stay, the backend answers calls into an absent component with a 409, and
 * switching it back on is lossless - which is why there is no warning dialog
 * about data, only about the restart.
 */
interface ComponentsBlockProps {
  /** Called after a finished run, so the version list above can re-read. */
  onChanged?: () => void;
}

export const ComponentsBlock: React.FC<ComponentsBlockProps> = ({ onChanged }) => {
  const { t } = useTranslation('admin');
  const { capabilities, refresh: refreshCapabilities } = useCapabilities();
  const [entries, setEntries] = useState<ComponentEntry[]>([]);
  const [saved, setSaved] = useState<ComponentProfile[]>([]);
  const [wanted, setWanted] = useState<ComponentProfile[]>([]);
  const [unreachable, setUnreachable] = useState(false);
  const [serverBusy, setServerBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [rebootRequired, setRebootRequired] = useState(false);
  const attached = useRef(false);

  const load = useCallback(async () => {
    try {
      const data = await componentsApi.get();
      setEntries(data.components);
      setSaved(data.profiles);
      setWanted(data.profiles);
      setUnreachable(!!data.unreachable);
      setServerBusy(data.busy);
    } catch {
      setUnreachable(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const changedRef = useRef(onChanged);
  changedRef.current = onChanged;

  const run = useComponentsRun(() => {
    void load();
    // The backend was recreated with the new COMPOSE_PROFILES, so this is the
    // moment its capabilities answer changes - and with it the whole
    // navigation.
    void refreshCapabilities();
    // A component that is gone has no container, so it drops out of the
    // version list above too.
    changedRef.current?.();
  });

  // Whether the box needs a restart is only known once a run has answered.
  useEffect(() => {
    if (run.status?.reboot_required) setRebootRequired(true);
  }, [run.status]);

  // A run that is already going when this page opens - started in another tab,
  // or here before a reload. Attaching to it is also what clears `serverBusy`
  // again: the poll ends, and the reload behind it brings the current state.
  const attach = run.attach;
  useEffect(() => {
    if (serverBusy && !attached.current) {
      attached.current = true;
      attach();
    }
  }, [serverBusy, attach]);

  const dirty = useMemo(
    () =>
      saved.length !== wanted.length ||
      saved.some((profile) => !wanted.includes(profile)),
    [saved, wanted],
  );

  const turningOff = saved.filter((profile) => !wanted.includes(profile));
  const turningOn = wanted.filter((profile) => !saved.includes(profile));

  const toggle = (profile: ComponentProfile, on: boolean) =>
    setWanted((prev) =>
      on ? [...prev, profile] : prev.filter((p) => p !== profile),
    );

  const handleApply = () => {
    setConfirmOpen(false);
    setRebootRequired(false);
    void run.start(wanted);
  };

  const stateLabel = (entry: ComponentEntry): string => {
    if (!entry.installed) return t('system.components_state_off');
    const state = capabilities[PROFILE_FEATURE[entry.profile]];
    if (state?.healthy) return t('system.components_state_running');
    if (state?.running) return t('system.components_state_unhealthy');
    return t('system.components_state_stopped');
  };

  const stateColor = (entry: ComponentEntry): 'success' | 'warning' | 'default' => {
    if (!entry.installed) return 'default';
    const state = capabilities[PROFILE_FEATURE[entry.profile]];
    if (state?.healthy) return 'success';
    return 'warning';
  };

  const names = (profiles: ComponentProfile[]) =>
    profiles.map((p) => t(`system.component_${p}` as never)).join(', ');

  if (loading) return null;

  const busy = run.running || serverBusy;

  return (
    <SettingsBlock
      title={t('system.components_title')}
      description={t('system.components_hint')}
      help={t('system.components_help')}
    >
      {unreachable && (
        <Alert severity="info">{t('system.components_unavailable')}</Alert>
      )}

      <Box>
        {entries.map((entry) => (
          <Box
            key={entry.profile}
            sx={{ display: 'flex', alignItems: 'center', gap: 1, minHeight: 42 }}
          >
            <FormControlLabel
              sx={{ flexGrow: 1, mr: 0 }}
              control={
                <Switch
                  checked={wanted.includes(entry.profile)}
                  onChange={(_, checked) => toggle(entry.profile, checked)}
                  disabled={busy || unreachable}
                  color="primary"
                />
              }
              label={
                <HelpLabel
                  text={t(`system.component_${entry.profile}` as never)}
                  help={t(`system.component_${entry.profile}_hint` as never)}
                />
              }
            />
            <Chip
              size="small"
              variant="outlined"
              color={stateColor(entry)}
              label={stateLabel(entry)}
            />
          </Box>
        ))}
      </Box>

      {rebootRequired && (
        // I2C only appears as /dev/i2c-1 after a restart, so the container of
        // a just-enabled card reader or display could not be started yet.
        <Alert severity="warning">{t('system.components_reboot_required')}</Alert>
      )}

      {dirty && (
        <Typography variant="caption" color="text.secondary">
          {t('system.components_restart_hint')}
        </Typography>
      )}

      <Box display="flex" flexWrap="wrap" gap={1} alignItems="center">
        <ActionButton
          actionType="primary"
          onClick={() => setConfirmOpen(true)}
          disabled={!dirty || busy || unreachable}
          loading={busy}
        >
          {t('system.components_apply')}
        </ActionButton>
        {dirty && !busy && (
          <ActionButton actionType="secondary" onClick={() => setWanted(saved)}>
            {t('actions.cancel', { ns: 'common' })}
          </ActionButton>
        )}
      </Box>

      <ConfirmDialog
        open={confirmOpen}
        title={t('system.components_apply')}
        message={[
          turningOn.length > 0
            ? t('system.components_confirm_on', { names: names(turningOn) })
            : null,
          turningOff.length > 0
            ? t('system.components_confirm_off', { names: names(turningOff) })
            : null,
          t('system.components_confirm_restart'),
        ]
          .filter(Boolean)
          .join(' ')}
        onCancel={() => setConfirmOpen(false)}
        onConfirm={handleApply}
      />

      <UpdateProgressDialog
        open={run.progressOpen}
        running={run.running}
        status={run.status}
        onClose={run.closeProgress}
        title={t('system.components_progress_title')}
        successText={t('system.components_success')}
        failedText={t('system.components_failed')}
        stepPrefix="system.components_step_"
      />
    </SettingsBlock>
  );
};
