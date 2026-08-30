import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  FormControlLabel,
  Switch,
  Typography,
} from '@mui/material';
import RefreshIcon from '@mui/icons-material/Refresh';
import { useTranslation } from 'react-i18next';
import { useToast } from '@/contexts/ToastContext';
import { systemApi, type UpdateCheckResponse } from '@/api/system';
import { useGeneralConfigField } from '@/hooks/useGeneralConfig';
import { ActionButton } from '@/components/ui/ActionButton';
import { SettingsBlock } from '@/components/admin/SettingsBlock';
import { translateApiError } from '@/utils/apiError';
import { ServiceVersionRow } from './ServiceVersionRow';
import { ReleaseNotesList } from './ReleaseNotesList';
import { UpdateProgressDialog } from './UpdateProgressDialog';
import { OsUpdateButton } from './OsUpdateButton';
import { CleanupButton } from './CleanupButton';
import { useUpdateRun } from './useUpdateRun';

/**
 * Welche Versionen laufen, was es Neues gibt, und die Knoepfe, die das aendern.
 *
 * Die Knopfreihe traegt bewusst auch OS-Update und Aufraeumen: das ist die
 * Reihe „was kann ich an dieser Box warten", und sie stand vor der Aufteilung
 * genauso da. Beide bringen ihren Zustand selbst mit.
 */
export const UpdateBlock: React.FC = () => {
  const { t, i18n } = useTranslation('admin');
  const { showError } = useToast();
  const [check, setCheck] = useState<UpdateCheckResponse | null>(null);
  const [checking, setChecking] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // force=false liest den zwischengespeicherten Stand - der Aufruf beim
  // Oeffnen der Seite soll niemanden auf eine Netzabfrage warten lassen.
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

  useEffect(() => { void loadCheck(false); }, [loadCheck]);

  const run = useUpdateRun(() => void loadCheck(true));

  const {
    value: autoCheck,
    setValue: setAutoCheck,
    save: saveAutoCheck,
  } = useGeneralConfigField('auto_update_check_enabled', false);

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

      {/* Frueher stand hier ein einzelner Commit-Hash des Arbeitsbaums. Der
          sagte nichts darueber, welche Images tatsaechlich laufen - jeder
          Dienst hat seine eigene Version. */}
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

      <FormControlLabel
        control={
          <Switch
            checked={autoCheck ?? false}
            onChange={(_, checked) => void handleAutoCheckChange(checked)}
            color="primary"
          />
        }
        label={t('system.auto_update_check')}
        sx={{ display: 'block', mb: 0.5 }}
      />
      <Typography variant="caption" display="block" color="text.secondary" sx={{ mb: 1.5 }}>
        {t('system.auto_update_check_hint')}
      </Typography>

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

      {/* Eigener Dialog statt ConfirmDialog: hier stehen die Aenderungsnotizen drin. */}
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
