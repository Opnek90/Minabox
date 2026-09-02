import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  FormControl,
  FormControlLabel,
  InputLabel,
  MenuItem,
  Select,
  Switch,
  Typography,
} from '@mui/material';
import RefreshIcon from '@mui/icons-material/Refresh';
import { useTranslation } from 'react-i18next';
import { useToast } from '@/contexts/ToastContext';
import {
  systemApi,
  type RollbackCandidate,
  type UpdateChannel,
  type UpdateCheckResponse,
} from '@/api/system';
import { useGeneralConfigField } from '@/hooks/useGeneralConfig';
import { ActionButton } from '@/components/ui/ActionButton';
import { SettingsBlock } from '@/components/admin/SettingsBlock';
import { translateApiError } from '@/utils/apiError';
import { HelpLabel, HelpTip } from '@/components/ui/HelpTip';
import { ServiceVersionRow } from './ServiceVersionRow';
import { ReleaseNotesList } from './ReleaseNotesList';
import { UpdateProgressDialog } from './UpdateProgressDialog';
import { RollbackSection } from './RollbackSection';
import { OsUpdateButton } from './OsUpdateButton';
import { CleanupButton } from './CleanupButton';
import { useUpdateRun } from './useUpdateRun';

interface UpdateBlockProps {
  /**
   * Bumped whenever the components of this box changed. The version list is
   * one row per *existing* container, so switching a component off drops it -
   * but this block reads that list once, when it mounts. Without the signal
   * the row of a component that is gone would stay on screen until the page
   * is reloaded.
   */
  refreshKey?: number;
}

/**
 * Which versions are running, what is new, and the buttons that change it.
 *
 * The button row deliberately carries the OS update and cleanup too: this is
 * the "what can I maintain on this box" row, and it looked the same before the
 * split. Both bring their own state.
 */
export const UpdateBlock: React.FC<UpdateBlockProps> = ({ refreshKey = 0 }) => {
  const { t, i18n } = useTranslation('admin');
  const { showError } = useToast();
  const [check, setCheck] = useState<UpdateCheckResponse | null>(null);
  const [candidates, setCandidates] = useState<RollbackCandidate[]>([]);
  const [checking, setChecking] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // force=false reads the cached state - the call when the page opens should
  // not make anyone wait for a network request.
  const loadCheck = useCallback(async (force: boolean) => {
    setError(null);
    if (force) setChecking(true);
    try {
      setCheck(await systemApi.getUpdateCheck(force));
    } catch {
      setError(t('system.check_failed'));
    } finally {
      setChecking(false);
      setLoading(false);
    }
  }, [t]);

  // The history is a separate read: it comes from the Host-Helper, not from
  // the manifest, and its absence must not take the version list with it.
  const loadHistory = useCallback(async () => {
    try {
      setCandidates((await systemApi.getUpdateHistory()).candidates);
    } catch {
      setCandidates([]);
    }
  }, []);

  useEffect(() => {
    void loadCheck(false);
    void loadHistory();
  }, [loadCheck, loadHistory]);

  // force: the components just changed, so the cached answer was computed for
  // a different box.
  useEffect(() => {
    if (refreshKey > 0) void loadCheck(true);
  }, [refreshKey, loadCheck]);

  const run = useUpdateRun(() => {
    void loadCheck(true);
    void loadHistory();
  });

  const {
    value: autoCheck,
    setValue: setAutoCheck,
    save: saveAutoCheck,
  } = useGeneralConfigField('auto_update_check_enabled', false);

  const {
    value: channel,
    setValue: setChannel,
    save: saveChannel,
  } = useGeneralConfigField('update_channel', 'stable');

  // A switched channel points at other versions, so the cached answer is not
  // just stale but about something else - hence the forced re-check.
  const handleChannelChange = async (next: UpdateChannel) => {
    const previous = channel ?? 'stable';
    setChannel(next);
    try {
      await saveChannel();
      await loadCheck(true);
    } catch (err) {
      setChannel(previous);
      showError(translateApiError(t, i18n, err));
    }
  };

  const handleAutoCheckChange = async (checked: boolean) => {
    setAutoCheck(checked);
    try {
      await saveAutoCheck();
    } catch (err) {
      setAutoCheck(!checked);
      showError(translateApiError(t, i18n, err));
    }
  };

  const pending = (check?.services ?? []).filter((s) => s.update_available);

  const handleUpdate = () => {
    setConfirmOpen(false);
    void run.start(
      Object.fromEntries(
        pending.filter((s) => s.latest).map((s) => [s.service, s.latest as string]),
      ),
    );
  };

  if (loading && !check) return null;

  return (
    <SettingsBlock title={t('system.maintenance_title')}>
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {/* This used to be a single commit hash of the working tree. It said
          nothing about which images are actually running - every service has
          its own version. */}
      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr' },
          columnGap: 2,
          rowGap: 0.5,
          mb: 1.5,
        }}
      >
        {(check?.services ?? []).map((svc) => (
          <ServiceVersionRow key={svc.service} service={svc} />
        ))}
      </Box>

      {check?.error ? (
        <Alert severity="warning" sx={{ mb: 1.5 }}>{t('system.check_unavailable')}</Alert>
      ) : pending.length > 0 ? (
        <Alert severity="info" sx={{ mb: 1.5 }}>
          {t('system.updates_available', { count: pending.length })}
        </Alert>
      ) : (
        check && <Alert severity="success" sx={{ mb: 1.5 }}>{t('system.up_to_date')}</Alert>
      )}

      <Box display="flex" alignItems="center" gap={0.5} sx={{ mb: 1.5 }}>
        <FormControl size="small" sx={{ minWidth: 200 }}>
          <InputLabel id="update-channel-label">{t('system.update_channel')}</InputLabel>
          <Select
            labelId="update-channel-label"
            value={channel ?? 'stable'}
            label={t('system.update_channel')}
            onChange={(e) => void handleChannelChange(e.target.value as UpdateChannel)}
          >
            <MenuItem value="stable">{t('system.update_channel_stable')}</MenuItem>
            <MenuItem value="beta">{t('system.update_channel_beta')}</MenuItem>
          </Select>
        </FormControl>
        <HelpTip
          title={t('system.update_channel_hint')}
          label={t('system.update_channel')}
        />
      </Box>

      <FormControlLabel
        control={
          <Switch
            checked={autoCheck ?? false}
            onChange={(_, checked) => void handleAutoCheckChange(checked)}
            color="primary"
          />
        }
        label={
          <HelpLabel
            text={t('system.auto_update_check')}
            help={t('system.auto_update_check_hint')}
          />
        }
        sx={{ display: 'block', mb: 1.5 }}
      />

      <Box display="flex" flexWrap="wrap" gap={1} alignItems="center">
        <ActionButton
          actionType="secondary"
          startIcon={<RefreshIcon />}
          onClick={() => void loadCheck(true)}
          disabled={checking}
          loading={checking}
        >
          {t('system.check_updates')}
        </ActionButton>
        {pending.length > 0 && (
          <ActionButton
            actionType="primary"
            onClick={() => setConfirmOpen(true)}
            disabled={run.running}
            loading={run.running}
          >
            {t('system.update_minabox')}
          </ActionButton>
        )}
        <OsUpdateButton />
        <CleanupButton />
      </Box>

      {check && (
        <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1 }}>
          {t('system.checked_at', { time: new Date(check.checked_at).toLocaleString() })}
        </Typography>
      )}

      <RollbackSection
        candidates={candidates}
        disabled={run.running}
        onRollback={(service) => void run.startRollback([service])}
      />

      {/* A dialog of its own instead of ConfirmDialog: the release notes go in here. */}
      <Dialog open={confirmOpen} onClose={() => setConfirmOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>{t('system.update_minabox')}</DialogTitle>
        <DialogContent>
          <DialogContentText sx={{ mb: 2 }}>{t('system.update_minabox_confirm')}</DialogContentText>
          <Alert severity="info" sx={{ mb: 2 }}>{t('system.update_backup_hint')}</Alert>
          <Typography variant="subtitle2" sx={{ mb: 1 }}>{t('system.changelog_title')}</Typography>
          {pending.map((svc) => (
            <ReleaseNotesList key={svc.service} service={svc} />
          ))}
        </DialogContent>
        <DialogActions>
          <ActionButton actionType="secondary" onClick={() => setConfirmOpen(false)}>
            {t('actions.cancel', { ns: 'common' })}
          </ActionButton>
          <ActionButton actionType="primary" onClick={handleUpdate}>
            {t('actions.confirm', { ns: 'common' })}
          </ActionButton>
        </DialogActions>
      </Dialog>

      <UpdateProgressDialog
        open={run.progressOpen}
        running={run.running}
        status={run.status}
        onClose={run.closeProgress}
      />
    </SettingsBlock>
  );
};
