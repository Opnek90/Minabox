import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Alert,
  Box,
  Checkbox,
  Chip,
  CircularProgress,
  Collapse,
  LinearProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  FormControlLabel,
  Switch,
  TextField,
  Typography,
} from '@mui/material';
import BackupIcon from '@mui/icons-material/Backup';
import CloudDownloadIcon from '@mui/icons-material/CloudDownload';
import ComputerIcon from '@mui/icons-material/Computer';
import PowerSettingsNewIcon from '@mui/icons-material/PowerSettingsNew';
import RestartAltIcon from '@mui/icons-material/RestartAlt';
import RestoreIcon from '@mui/icons-material/Restore';
import RefreshIcon from '@mui/icons-material/Refresh';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutline';
import { useTranslation } from 'react-i18next';
import { useToast } from '@/contexts/ToastContext';
import { configApi } from '@/api/config';
import {
  systemApi,
  type ServiceUpdateInfo,
  type UpdateCheckResponse,
  type UpdateStatusResponse,
} from '@/api/system';
import { ActionButton } from '@/components/ui/ActionButton';
import { SettingsBlock } from '@/components/admin/SettingsBlock';
import { translateApiError } from '@/utils/apiError';

/** Eine Zeile der Versionsliste: Dienst, laufende Version, Hinweis auf Neues. */
const ServiceVersionRow: React.FC<{ service: ServiceUpdateInfo }> = ({ service }) => {
  const { t } = useTranslation('admin');
  return (
    <Box display="flex" alignItems="baseline" gap={1} sx={{ minWidth: 0 }}>
      <Typography
        variant="body2"
        sx={{ textTransform: 'capitalize', flex: 1, minWidth: 0 }}
        noWrap
      >
        {service.service}
      </Typography>
      <Typography
        variant="body2"
        color="text.secondary"
        sx={{ fontVariantNumeric: 'tabular-nums' }}
      >
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

/** Aenderungsnotizen einer Ausgabe in der eingestellten Sprache. */
const ReleaseNotesList: React.FC<{ service: ServiceUpdateInfo }> = ({ service }) => {
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

export const SystemMaintenanceSection: React.FC = () => {
  const { t, i18n } = useTranslation('admin');
  const { showSuccess, showError } = useToast();
  const [check, setCheck] = useState<UpdateCheckResponse | null>(null);
  const [checking, setChecking] = useState(false);
  const [updateStatus, setUpdateStatus] = useState<UpdateStatusResponse | null>(null);
  const [updateLogOpen, setUpdateLogOpen] = useState(false);
  const [updateProgressOpen, setUpdateProgressOpen] = useState(false);
  const [restartDialogOpen, setRestartDialogOpen] = useState(false);
  const [rebootDialogOpen, setRebootDialogOpen] = useState(false);
  const [shutdownDialogOpen, setShutdownDialogOpen] = useState(false);
  const [restoreDialogOpen, setRestoreDialogOpen] = useState(false);
  const [restoreFile, setRestoreFile] = useState<File | null>(null);
  const [restorePending, setRestorePending] = useState(false);
  const [updateDialogOpen, setUpdateDialogOpen] = useState(false);
  const [updateOsDialogOpen, setUpdateOsDialogOpen] = useState(false);
  const [updating, setUpdating] = useState(false);
  const [updatingOs, setUpdatingOs] = useState(false);
  // Merkt sich, dass der Abschluss dieses Update-Laufs bereits gemeldet wurde.
  // Ohne diesen Riegel feuert die 2-Sekunden-Abfrage die Erfolgsmeldung bei
  // jedem weiteren Durchlauf erneut (#137).
  const updateOutcomeNotifiedRef = useRef(false);
  const [dockerPruneDialogOpen, setDockerPruneDialogOpen] = useState(false);
  const [dockerPrunePending, setDockerPrunePending] = useState(false);
  const [updateOsLogOpen, setUpdateOsLogOpen] = useState(false);
  const [updateOsLog, setUpdateOsLog] = useState('');
  const [updateOsLogRunning, setUpdateOsLogRunning] = useState(false);
  const [factoryResetDialogOpen, setFactoryResetDialogOpen] = useState(false);
  const [factoryResetDeleteAudio, setFactoryResetDeleteAudio] = useState(false);
  const [factoryResetConfirmText, setFactoryResetConfirmText] = useState('');
  const [factoryResetPending, setFactoryResetPending] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [autoUpdateCheck, setAutoUpdateCheck] = useState(false);

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

  useEffect(() => { loadCheck(false); }, [loadCheck]);

  useEffect(() => {
    configApi.getGeneral()
      .then((g) => setAutoUpdateCheck(g.auto_update_check_enabled ?? false))
      .catch(() => {});
  }, []);

  const handleAutoUpdateCheckChange = async (checked: boolean) => {
    setAutoUpdateCheck(checked);
    try {
      await configApi.updateGeneral({ auto_update_check_enabled: checked });
    } catch (err) {
      setAutoUpdateCheck(!checked);
      showError(translateApiError(t, i18n, err));
    }
  };

  const fetchUpdateOsLog = useCallback(async () => {
    try {
      const data = await systemApi.getUpdateOsLog();
      setUpdateOsLog(data.log ?? '');
      setUpdateOsLogRunning(data.running ?? false);
    } catch {
      setUpdateOsLogRunning(false);
    }
  }, []);

  useEffect(() => {
    if (!updateOsLogOpen) return;
    fetchUpdateOsLog();
    const interval = setInterval(fetchUpdateOsLog, 2000);
    return () => clearInterval(interval);
  }, [updateOsLogOpen, fetchUpdateOsLog]);

  const handleRestart = async () => {
    setRestartDialogOpen(false);
    try { await systemApi.restart(); } catch { /* restarting */ }
  };

  const handleReboot = async () => {
    setRebootDialogOpen(false);
    try { await systemApi.rebootHost(); } catch { /* connection drops */ }
  };

  const handleShutdown = async () => {
    setShutdownDialogOpen(false);
    try { await systemApi.shutdownHost(); } catch { /* connection drops */ }
  };

  const handleDownloadBackup = async () => {
    try {
      const blob = await systemApi.downloadBackup();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `minabox-backup-${new Date().toISOString().slice(0, 10)}.zip`;
      a.click();
      URL.revokeObjectURL(url);
      showSuccess(t('system.backup_download_success'));
    } catch (err) {
      showError(translateApiError(t, i18n, err));
    }
  };

  const handleRestoreBackup = async () => {
    if (!restoreFile) return;
    setRestorePending(true);
    setRestoreDialogOpen(false);
    try {
      await systemApi.restoreBackup(restoreFile);
      setRestoreFile(null);
      showSuccess(t('system.backup_restore_success'));
    } catch (err) {
      showError(translateApiError(t, i18n, err));
    } finally {
      setRestorePending(false);
    }
  };

  /**
   * `targets` leer lassen heisst "alles auf den neuesten Stand"; mit Zielen
   * werden genau diese Dienste bewegt.
   */
  const startUpdate = async (targets?: Record<string, string>) => {
    setUpdateDialogOpen(false);
    setUpdating(true);
    setUpdateStatus(null);
    updateOutcomeNotifiedRef.current = false;
    try {
      await systemApi.updateMinabox(targets);
      // Der Aufruf kehrt sofort zurueck; ab hier zeigt das Fortschrittsfenster,
      // was passiert.
      setUpdateProgressOpen(true);
    } catch (err: unknown) {
      showError(translateApiError(t, i18n, err));
      setUpdating(false);
    }
  };

  const handleUpdateMinabox = () =>
    startUpdate(
      Object.fromEntries(
        pendingUpdates
          .filter((svc) => svc.latest)
          .map((svc) => [svc.service, svc.latest as string]),
      ),
    );

  // Waehrend des Updates startet die Box Backend und WebUI neu - die Abfrage
  // schlaegt dann kurz fehl. Das ist kein Fehler, sondern der Neustart selbst,
  // also wird einfach weiter gefragt.
  useEffect(() => {
    if (!updateProgressOpen) return;
    let active = true;
    let interval: ReturnType<typeof setInterval> | undefined;
    const stop = () => { if (interval) { clearInterval(interval); interval = undefined; } };
    const poll = async () => {
      try {
        const status = await systemApi.getUpdateStatus();
        if (!active) return;
        setUpdateStatus(status);
        if (!status.running && status.exit_code !== null) {
          setUpdating(false);
          // Endzustand nur einmal je Update-Lauf melden und danach nicht mehr
          // abfragen - sonst wiederholt sich die Meldung im Sekundentakt (#137).
          stop();
          if (!updateOutcomeNotifiedRef.current) {
            updateOutcomeNotifiedRef.current = true;
            if (status.exit_code === 0) {
              showSuccess(t('system.update_success'));
              loadCheck(true);
            } else {
              showError(t('system.update_failed'));
            }
          }
        }
      } catch {
        if (active) setUpdateStatus((prev) => (prev ? { ...prev, unreachable: true } : prev));
      }
    };
    poll();
    interval = setInterval(poll, 2000);
    return () => { active = false; stop(); };
  }, [updateProgressOpen, showSuccess, showError, t, loadCheck]);

  const handleUpdateOs = async () => {
    setUpdateOsDialogOpen(false);
    setUpdatingOs(true);
    try {
      await systemApi.updateOs();
      showSuccess(t('system.update_os_success'));
      setUpdateOsLogOpen(true);
    } catch (err: unknown) {
      showError(translateApiError(t, i18n, err));
    } finally {
      setUpdatingOs(false);
    }
  };

  const handleDockerPrune = async () => {
    setDockerPruneDialogOpen(false);
    setDockerPrunePending(true);
    try {
      await systemApi.dockerPrune();
      showSuccess(t('system.cleanup_success'));
    } catch (err: unknown) {
      showError(translateApiError(t, i18n, err));
    } finally {
      setDockerPrunePending(false);
    }
  };

  const handleFactoryReset = async () => {
    const confirmWord = t('system.factory_reset_confirm_word');
    if (factoryResetConfirmText.trim() !== confirmWord) return;
    setFactoryResetDialogOpen(false);
    setFactoryResetConfirmText('');
    setFactoryResetPending(true);
    try {
      await systemApi.factoryReset(factoryResetDeleteAudio);
      showSuccess(t('system.factory_reset_success'));
    } catch (err) {
      showError(translateApiError(t, i18n, err));
    } finally {
      setFactoryResetPending(false);
    }
  };

  const pendingUpdates = (check?.services ?? []).filter((s) => s.update_available);

  const factoryResetConfirmValid = factoryResetConfirmText.trim() === t('system.factory_reset_confirm_word');

  if (loading && !check) return null;

  return (
    <Box>
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {/* ── Sicherung ───────────────────────────────────────────────────────── */}
      <SettingsBlock title={t('system.backup_title')}>
        <Box display="flex" flexWrap="wrap" gap={1} alignItems="center">
          <ActionButton
            actionType="secondary"
            startIcon={<CloudDownloadIcon />}
            onClick={handleDownloadBackup}
          >
            {t('system.backup_download')}
          </ActionButton>
          <ActionButton
            actionType="secondary"
            startIcon={<BackupIcon />}
            onClick={() => setRestoreDialogOpen(true)}
            disabled={restorePending}
            loading={restorePending}
          >
            {t('system.backup_restore')}
          </ActionButton>
        </Box>
      </SettingsBlock>

      {/* ── Version & Update ─────────────────────────────────────────────────── */}
      <SettingsBlock title={t('system.maintenance_title')}>
        {/* Frueher stand hier ein einzelner Commit-Hash des Arbeitsbaums. Der
            sagte nichts darueber, welche Images tatsaechlich laufen - jeder
            Dienst hat seine eigene Version (docs/Versionierung.md). */}
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
          <Alert severity="warning" sx={{ mb: 1.5 }}>
            {t('system.check_unavailable')}
          </Alert>
        ) : pendingUpdates.length > 0 ? (
          <Alert severity="info" sx={{ mb: 1.5 }}>
            {t('system.updates_available', { count: pendingUpdates.length })}
          </Alert>
        ) : (
          check && (
            <Alert severity="success" sx={{ mb: 1.5 }}>
              {t('system.up_to_date')}
            </Alert>
          )
        )}

        <FormControlLabel
          control={
            <Switch
              checked={autoUpdateCheck}
              onChange={(_, checked) => handleAutoUpdateCheckChange(checked)}
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
            onClick={() => loadCheck(true)}
            disabled={checking}
            loading={checking}
          >
            {t('system.check_updates')}
          </ActionButton>
          {pendingUpdates.length > 0 && (
            <ActionButton
              actionType="primary"
              onClick={() => setUpdateDialogOpen(true)}
              disabled={updating}
              loading={updating}
            >
              {t('system.update_minabox')}
            </ActionButton>
          )}
          <ActionButton
            actionType="secondary"
            onClick={() => setUpdateOsDialogOpen(true)}
            disabled={updatingOs}
            loading={updatingOs}
          >
            {t('system.update_os')}
          </ActionButton>
          <ActionButton
            actionType="destructive"
            onClick={() => setDockerPruneDialogOpen(true)}
            disabled={dockerPrunePending}
          >
            {t('system.cleanup')}
          </ActionButton>
        </Box>

        {check && (
          <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1 }}>
            {t('system.checked_at', { time: new Date(check.checked_at).toLocaleString() })}
          </Typography>
        )}
      </SettingsBlock>

      {/* ── Neustart ─────────────────────────────────────────────────────────── */}
      <SettingsBlock title={t('system.restart_group')}>
        {/* Zwei feste Reihen statt eines umbrechenden Blocks: oben, was den
            Betrieb nur unterbricht, unten, was ihn beendet oder Daten loescht.
            Beim Umbruch nach Breite landete "Herunterfahren" sonst neben den
            harmlosen Neustarts. */}
        <Box display="flex" flexWrap="wrap" gap={1}>
          <ActionButton actionType="secondary" startIcon={<RestartAltIcon />} onClick={() => setRestartDialogOpen(true)}>
            {t('system.restart')}
          </ActionButton>
          <ActionButton actionType="secondary" startIcon={<ComputerIcon />} onClick={() => setRebootDialogOpen(true)}>
            {t('system.reboot')}
          </ActionButton>
        </Box>
        <Box display="flex" flexWrap="wrap" gap={1} sx={{ mt: 1 }}>
          <ActionButton actionType="destructive" startIcon={<PowerSettingsNewIcon />} onClick={() => setShutdownDialogOpen(true)}>
            {t('system.shutdown')}
          </ActionButton>
          <ActionButton
            actionType="destructive"
            startIcon={<RestoreIcon />}
            onClick={() => { setFactoryResetDialogOpen(true); setFactoryResetConfirmText(''); }}
            disabled={factoryResetPending}
          >
            {t('system.factory_reset')}
          </ActionButton>
        </Box>
      </SettingsBlock>

      {/* ── Dialogs ─────────────────────────────────────────────────────────── */}
      <Dialog open={restartDialogOpen} onClose={() => setRestartDialogOpen(false)}>
        <DialogTitle>{t('system.restart')}</DialogTitle>
        <DialogContent><DialogContentText>{t('system.restart_confirm')}</DialogContentText></DialogContent>
        <DialogActions>
          <ActionButton actionType="secondary" onClick={() => setRestartDialogOpen(false)}>
            {t('actions.cancel', { ns: 'common' })}
          </ActionButton>
          <ActionButton actionType="destructive" onClick={handleRestart}>
            {t('actions.confirm', { ns: 'common' })}
          </ActionButton>
        </DialogActions>
      </Dialog>

      <Dialog open={rebootDialogOpen} onClose={() => setRebootDialogOpen(false)}>
        <DialogTitle>{t('system.reboot')}</DialogTitle>
        <DialogContent><DialogContentText>{t('system.reboot_confirm')}</DialogContentText></DialogContent>
        <DialogActions>
          <ActionButton actionType="secondary" onClick={() => setRebootDialogOpen(false)}>
            {t('actions.cancel', { ns: 'common' })}
          </ActionButton>
          <ActionButton actionType="destructive" onClick={handleReboot}>
            {t('actions.confirm', { ns: 'common' })}
          </ActionButton>
        </DialogActions>
      </Dialog>

      <Dialog open={shutdownDialogOpen} onClose={() => setShutdownDialogOpen(false)}>
        <DialogTitle>{t('system.shutdown')}</DialogTitle>
        <DialogContent><DialogContentText>{t('system.shutdown_confirm')}</DialogContentText></DialogContent>
        <DialogActions>
          <ActionButton actionType="secondary" onClick={() => setShutdownDialogOpen(false)}>
            {t('actions.cancel', { ns: 'common' })}
          </ActionButton>
          <ActionButton actionType="destructive" onClick={handleShutdown}>
            {t('actions.confirm', { ns: 'common' })}
          </ActionButton>
        </DialogActions>
      </Dialog>

      <Dialog open={factoryResetDialogOpen} onClose={() => { setFactoryResetDialogOpen(false); setFactoryResetConfirmText(''); }}>
        <DialogTitle>{t('system.factory_reset')}</DialogTitle>
        <DialogContent>
          <DialogContentText sx={{ mb: 2 }}>{t('system.factory_reset_warning')}</DialogContentText>
          <FormControlLabel control={<Checkbox checked={factoryResetDeleteAudio} onChange={(_, c) => setFactoryResetDeleteAudio(c)} color="primary" />} label={t('system.factory_reset_delete_audio')} sx={{ display: 'block', mb: 2 }} />
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>{t('system.factory_reset_type_prompt')}</Typography>
          <TextField fullWidth size="small" value={factoryResetConfirmText} onChange={(e) => setFactoryResetConfirmText(e.target.value)} placeholder={t('system.factory_reset_confirm_word')} autoComplete="off" />
        </DialogContent>
        <DialogActions>
          <ActionButton
            actionType="secondary"
            onClick={() => { setFactoryResetDialogOpen(false); setFactoryResetConfirmText(''); }}
          >
            {t('actions.cancel', { ns: 'common' })}
          </ActionButton>
          <ActionButton
            actionType="destructive"
            onClick={handleFactoryReset}
            disabled={!factoryResetConfirmValid || factoryResetPending}
          >
            {t('actions.confirm', { ns: 'common' })}
          </ActionButton>
        </DialogActions>
      </Dialog>

      <Dialog open={restoreDialogOpen} onClose={() => { setRestoreDialogOpen(false); setRestoreFile(null); }}>
        <DialogTitle>{t('system.backup_restore')}</DialogTitle>
        <DialogContent>
          <DialogContentText sx={{ mb: 2 }}>{t('system.backup_restore_confirm')}</DialogContentText>
          <Box
            component="label"
            sx={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              minHeight: 40,
              px: 2.5,
              py: 0.75,
              fontSize: '0.9rem',
              fontWeight: 600,
              letterSpacing: 0,
              border: '1px solid',
              borderColor: 'primary.main',
              color: 'primary.main',
              borderRadius: 1,
              cursor: 'pointer',
              width: '100%',
              '&:hover': { bgcolor: 'action.hover' },
            }}
          >
            {t('system.backup_restore_select')}
            <input
              type="file"
              hidden
              accept=".zip"
              onChange={(e) => setRestoreFile(e.target.files?.[0] ?? null)}
            />
          </Box>
          {restoreFile && <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>{restoreFile.name}</Typography>}
        </DialogContent>
        <DialogActions>
          <ActionButton
            actionType="secondary"
            onClick={() => { setRestoreDialogOpen(false); setRestoreFile(null); }}
          >
            {t('actions.cancel', { ns: 'common' })}
          </ActionButton>
          <ActionButton
            actionType="destructive"
            onClick={handleRestoreBackup}
            disabled={!restoreFile}
          >
            {t('system.backup_restore')}
          </ActionButton>
        </DialogActions>
      </Dialog>

      <Dialog
        open={updateDialogOpen}
        onClose={() => setUpdateDialogOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>{t('system.update_minabox')}</DialogTitle>
        <DialogContent>
          <DialogContentText sx={{ mb: 2 }}>{t('system.update_minabox_confirm')}</DialogContentText>
          <Alert severity="info" sx={{ mb: 2 }}>{t('system.update_backup_hint')}</Alert>
          <Typography variant="subtitle2" sx={{ mb: 1 }}>{t('system.changelog_title')}</Typography>
          {pendingUpdates.map((svc) => (
            <ReleaseNotesList key={svc.service} service={svc} />
          ))}
        </DialogContent>
        <DialogActions>
          <ActionButton actionType="secondary" onClick={() => setUpdateDialogOpen(false)}>
            {t('actions.cancel', { ns: 'common' })}
          </ActionButton>
          <ActionButton actionType="primary" onClick={handleUpdateMinabox}>
            {t('actions.confirm', { ns: 'common' })}
          </ActionButton>
        </DialogActions>
      </Dialog>

      {/* ── Fortschritt des Updates ───────────────────────────────────────── */}
      <Dialog
        open={updateProgressOpen}
        // Kein Schliessen per Klick daneben, solange es laeuft: das Fenster ist
        // die einzige Stelle, an der man sieht, was gerade mit der Box passiert.
        onClose={() => { if (!updating) setUpdateProgressOpen(false); }}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>{t('system.update_progress_title')}</DialogTitle>
        <DialogContent>
          <Box display="flex" alignItems="center" gap={1.5} sx={{ mb: 1 }}>
            {updating ? (
              <CircularProgress size={22} />
            ) : updateStatus?.exit_code === 0 ? (
              <CheckCircleIcon color="success" />
            ) : (
              <ErrorOutlineIcon color="error" />
            )}
            <Box minWidth={0}>
              <Typography variant="body2">
                {updateStatus?.step != null && updateStatus?.step_count != null
                  ? t('system.update_step', { step: updateStatus.step,
                      count: updateStatus.step_count })
                  : t('system.update_starting')}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {!updating && updateStatus?.exit_code === 0
                  ? t('system.update_success')
                  : !updating && updateStatus?.exit_code != null
                    ? t('system.update_failed')
                    : updateStatus?.step_key
                      // step_key kommt vom Backend/Orchestrierungsskript und ist nicht
                      // an eine feste Werte-Menge gebunden - Key statisch pruefen geht nicht.
                      ? t(`system.update_step_${updateStatus.step_key}` as never)
                      : ''}
              </Typography>
            </Box>
          </Box>

          {updating && (
            <LinearProgress
              variant={
                updateStatus?.step != null && updateStatus?.step_count
                  ? 'determinate'
                  : 'indeterminate'
              }
              value={
                updateStatus?.step != null && updateStatus?.step_count
                  ? (updateStatus.step / updateStatus.step_count) * 100
                  : undefined
              }
              sx={{ mb: 1.5, height: 6, borderRadius: 3 }}
            />
          )}

          {updateStatus?.unreachable && updating && (
            // Genau das ist der Neustart der Dienste - kein Fehler, sondern der
            // erwartete Teil des Updates.
            <Alert severity="info" sx={{ mb: 1.5 }}>
              {t('system.update_reconnecting')}
            </Alert>
          )}

          <ActionButton
            actionType="secondary"
            startIcon={<ExpandMoreIcon
              sx={{ transform: updateLogOpen ? 'rotate(180deg)' : 'none', transition: '0.2s' }}
            />}
            onClick={() => setUpdateLogOpen((open) => !open)}
          >
            {updateLogOpen ? t('system.update_details_hide') : t('system.update_details_show')}
          </ActionButton>

          <Collapse in={updateLogOpen}>
            <Box
              component="pre"
              sx={{
                whiteSpace: 'pre-wrap',
                fontFamily: 'monospace',
                fontSize: '0.75rem',
                maxHeight: 360,
                overflow: 'auto',
                p: 1,
                mt: 1,
                bgcolor: 'action.hover',
                borderRadius: 1,
              }}
            >
              {updateStatus?.log || t('system.update_os_log_empty')}
            </Box>
          </Collapse>
        </DialogContent>
        <DialogActions>
          <ActionButton
            actionType="secondary"
            onClick={() => setUpdateProgressOpen(false)}
            disabled={updating}
          >
            {t('actions.close', { ns: 'common' })}
          </ActionButton>
        </DialogActions>
      </Dialog>

      <Dialog open={updateOsDialogOpen} onClose={() => setUpdateOsDialogOpen(false)}>
        <DialogTitle>{t('system.update_os')}</DialogTitle>
        <DialogContent><DialogContentText>{t('system.update_os_confirm')}</DialogContentText></DialogContent>
        <DialogActions>
          <ActionButton actionType="secondary" onClick={() => setUpdateOsDialogOpen(false)}>
            {t('actions.cancel', { ns: 'common' })}
          </ActionButton>
          <ActionButton
            actionType="primary"
            onClick={handleUpdateOs}
            disabled={updatingOs}
          >
            {t('actions.confirm', { ns: 'common' })}
          </ActionButton>
        </DialogActions>
      </Dialog>

      <Dialog open={updateOsLogOpen} onClose={() => setUpdateOsLogOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle>{t('system.update_os_log_title')}</DialogTitle>
        <DialogContent>
          {updateOsLogRunning && <Typography variant="caption" color="primary" display="block" sx={{ mb: 1 }}>{t('system.update_os_log_running')}</Typography>}
          <Box component="pre" sx={{ whiteSpace: 'pre-wrap', fontFamily: 'monospace', fontSize: '0.75rem', maxHeight: 400, overflow: 'auto', p: 1, bgcolor: 'action.hover', borderRadius: 1 }}>
            {updateOsLog || t('system.update_os_log_empty')}
          </Box>
        </DialogContent>
        <DialogActions>
          <ActionButton actionType="secondary" onClick={() => setUpdateOsLogOpen(false)}>
            {t('actions.close', { ns: 'common' })}
          </ActionButton>
        </DialogActions>
      </Dialog>

      <Dialog open={dockerPruneDialogOpen} onClose={() => setDockerPruneDialogOpen(false)}>
        <DialogTitle>{t('system.cleanup')}</DialogTitle>
        <DialogContent><DialogContentText>{t('system.cleanup_confirm')}</DialogContentText></DialogContent>
        <DialogActions>
          <ActionButton actionType="secondary" onClick={() => setDockerPruneDialogOpen(false)}>
            {t('actions.cancel', { ns: 'common' })}
          </ActionButton>
          <ActionButton
            actionType="destructive"
            onClick={handleDockerPrune}
            disabled={dockerPrunePending}
          >
            {t('actions.confirm', { ns: 'common' })}
          </ActionButton>
        </DialogActions>
      </Dialog>
    </Box>
  );
};
