import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Alert,
  Box,
  Checkbox,
  List,
  ListItem,
  ListItemText,
  Chip,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  FormControlLabel,
  MenuItem,
  Select,
  Stack,
  Typography,
} from '@mui/material';
import Accordion from '@mui/material/Accordion';
import AccordionDetails from '@mui/material/AccordionDetails';
import AccordionSummary from '@mui/material/AccordionSummary';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import LockIcon from '@mui/icons-material/Lock';
import { ActionButton } from '@/components/ui/ActionButton';
import { ResponsiveDialog } from '@/components/common/ResponsiveDialog';
import {
  systemApi,
  type DebugExportMediaLevel,
  type DebugExportOptions,
  type DebugExportPreview,
} from '@/api/system';
import { collectClientContext } from '@/utils/debugRingBuffer';

type Preset = 'minimal' | 'recommended' | 'full';

interface Selection {
  logs: boolean;
  settings: boolean;
  network: boolean;
  media: DebugExportMediaLevel;
  history: boolean;
  client: boolean;
  include_db: boolean;
}

const PRESET_VALUES: Record<Preset, Selection> = {
  minimal: {
    logs: false, settings: false, network: true, media: 'off',
    history: false, client: false, include_db: false,
  },
  recommended: {
    logs: true, settings: true, network: true, media: 'counts',
    history: false, client: true, include_db: false,
  },
  full: {
    logs: true, settings: true, network: true, media: 'filenames',
    history: true, client: true, include_db: false,
  },
};

interface DebugExportDialogProps {
  open: boolean;
  onClose: () => void;
}

/**
 * Dialog for the debug export.
 *
 * Every block states what it contains, what it helps with and what it does
 * *not* contain — the third line is the one that answers the question a user
 * actually has. The privacy notice stays visible rather than hiding behind an
 * expander: a data export that explains itself only when asked looks like one
 * with something to hide.
 */
export const DebugExportDialog: React.FC<DebugExportDialogProps> = ({ open, onClose }) => {
  const { t } = useTranslation('admin');
  const [preset, setPreset] = useState<Preset>('recommended');
  const [selection, setSelection] = useState<Selection>(PRESET_VALUES.recommended);
  const [elevated, setElevated] = useState(true);
  const [busy, setBusy] = useState(false);
  // Blocks a second submit within the same tick, before `busy` re-renders.
  const inFlight = useRef(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [dbConfirmed, setDbConfirmed] = useState(false);
  const [preview, setPreview] = useState<DebugExportPreview | null>(null);

  useEffect(() => {
    if (!open) return;
    setError(null);
    setDone(false);
    setPreview(null);
    systemApi
      .getDebugExportCapabilities()
      .then((caps) => setElevated(caps.elevated))
      // Capability lookup is a nicety: if it fails we still let the user try,
      // and the backend enforces the tier regardless.
      .catch(() => setElevated(false));
  }, [open]);

  const applyPreset = useCallback((next: Preset) => {
    setPreset(next);
    setSelection(PRESET_VALUES[next]);
    setDbConfirmed(false);
  }, []);

  const update = useCallback(<K extends keyof Selection>(key: K, value: Selection[K]) => {
    setSelection((current) => ({ ...current, [key]: value }));
  }, []);

  const options: DebugExportOptions = useMemo(
    () => ({
      preset,
      system: true,
      logs: selection.logs,
      settings: selection.settings,
      network: selection.network,
      media: selection.media,
      history: selection.history,
      client: selection.client,
      include_db: selection.include_db && dbConfirmed,
    }),
    [preset, selection, dbConfirmed]
  );

  const saveBlob = useCallback((blob: Blob, filename: string) => {
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }, []);

  const describeError = useCallback(
    (e: unknown) => {
      const response = (e as {
        response?: { status?: number; data?: { detail?: unknown } };
      })?.response;
      const status = response?.status;
      const detail = response?.data?.detail;
      // The backend sends a code for the two different 429 reasons; older
      // builds send a plain string, so fall back on the status alone.
      const code =
        detail && typeof detail === 'object'
          ? (detail as { code?: string }).code
          : undefined;

      if (code === 'export_in_progress') return t('system.debug_export.error_in_progress');
      if (code === 'export_rate_limited') return t('system.debug_export.error_rate_limited');
      if (status === 429) return t('system.debug_export.error_in_progress');
      if (status === 403) return t('system.debug_export.error_remote');
      if (status === 404) return t('system.debug_export.preview_expired');
      return t('system.debug_export.error');
    },
    [t]
  );

  const handlePreview = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError(null);
    setDone(false);
    try {
      const result = await systemApi.previewDebugExport(
        options,
        selection.client ? collectClientContext() : undefined
      );
      setPreview(result);
    } catch (e) {
      setError(describeError(e));
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }, [options, selection.client, describeError]);

  const handlePreviewDownload = useCallback(async () => {
    if (!preview || inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError(null);
    try {
      const blob = await systemApi.downloadDebugExport(preview.export_id);
      saveBlob(blob, preview.filename);
      setPreview(null);
      setDone(true);
    } catch (e) {
      setError(describeError(e));
      // The cached archive is gone after an expiry, so the preview must go too.
      setPreview(null);
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }, [preview, saveBlob, describeError]);

  const handleCreate = useCallback(async () => {
    // The disabled prop only takes effect after a re-render; a fast second
    // click otherwise slips through and the box answers the second POST with
    // 429. This ref blocks it in the same tick.
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError(null);
    setDone(false);
    try {
      const blob = await systemApi.createDebugExport(
        options,
        selection.client ? collectClientContext() : undefined
      );
      const stamp = new Date().toISOString().slice(0, 16).replace(/[:T]/g, '-');
      saveBlob(blob, `minabox-debug-${stamp}.zip`);
      setDone(true);
    } catch (e) {
      setError(describeError(e));
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }, [options, selection.client, saveBlob, describeError]);

  const formatBytes = (bytes: number): string =>
    bytes >= 1024 * 1024
      ? `${(bytes / 1024 / 1024).toFixed(1)} MB`
      : `${Math.max(1, Math.round(bytes / 1024))} KB`;

  const renderBlock = (
    key: keyof Selection | 'system',
    checked: boolean,
    onToggle?: (value: boolean) => void,
    extras?: React.ReactNode
  ) => {
    // The option is called include_db, its texts live under `database`.
    // `base` ist aus einem geschlossenen Set (keyof Selection) gebaut, bleibt aber
    // fuer TS ein generischer string - die vier t()-Aufrufe unten sind deshalb
    // per `as never` von der Key-Pruefung ausgenommen.
    const base = `system.debug_export.blocks.${key === 'include_db' ? 'database' : key}`;
    const locked = onToggle === undefined ? false : !elevated && (key === 'history' || key === 'include_db');
    const goodToKnow = key === 'history' || key === 'include_db';
    return (
      <Accordion key={key} disableGutters elevation={0} sx={{ '&:before': { display: 'none' } }}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />} sx={{ px: 1 }}>
          <FormControlLabel
            onClick={(event) => event.stopPropagation()}
            onFocus={(event) => event.stopPropagation()}
            control={
              <Checkbox
                checked={checked}
                disabled={!onToggle || locked}
                onChange={(event) => onToggle?.(event.target.checked)}
              />
            }
            label={
              <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
                <Typography variant="body2">
                  {t(`${base}.label` as never)}
                </Typography>
                {!onToggle && (
                  <Chip size="small" variant="outlined" label={t('system.debug_export.always_on')} />
                )}
                {locked && <LockIcon fontSize="small" color="disabled" />}
              </Stack>
            }
          />
        </AccordionSummary>
        <AccordionDetails sx={{ pt: 0 }}>
          <Stack spacing={1}>
            <Typography variant="caption" color="text.secondary">
              <strong>{t('system.debug_export.contains')}:</strong> {t(`${base}.contains` as never)}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              <strong>{t('system.debug_export.helps')}:</strong> {t(`${base}.helps` as never)}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              <strong>
                {goodToKnow
                  ? t('system.debug_export.good_to_know')
                  : t('system.debug_export.not_included')}
                :
              </strong>{' '}
              {goodToKnow ? t(`${base}.good_to_know` as never) : t(`${base}.not_included` as never)}
            </Typography>
            {locked && (
              <Typography variant="caption" color="warning.main">
                {t('system.debug_export.locked_hint')}
              </Typography>
            )}
            {extras}
          </Stack>
        </AccordionDetails>
      </Accordion>
    );
  };

  return (
    <ResponsiveDialog open={open} onClose={busy ? undefined : onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{t('system.debug_export.title')}</DialogTitle>
      <DialogContent dividers>
        {preview ? (
          <Stack spacing={2}>
            <Typography variant="subtitle2">
              {t('system.debug_export.preview_title')}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {t('system.debug_export.preview_hint')}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {t('system.debug_export.preview_size', { size: formatBytes(preview.total_bytes) })}
            </Typography>
            {preview.collectors_failed.length > 0 && (
              <Alert severity="warning">
                {t('system.debug_export.preview_failed_parts', { names: preview.collectors_failed.map((c) => c.name).join(', ') })}
              </Alert>
            )}
            <List dense disablePadding sx={{ maxHeight: 360, overflowY: 'auto' }}>
              {preview.files.map((file) => (
                <ListItem key={file.path} disableGutters divider>
                  <ListItemText
                    primary={
                      <Typography variant="body2">{file.description}</Typography>
                    }
                    secondary={
                      <Typography variant="caption" color="text.secondary">
                        {file.path} · {formatBytes(file.bytes)}
                      </Typography>
                    }
                  />
                </ListItem>
              ))}
            </List>
            {error && <Alert severity="error">{error}</Alert>}
          </Stack>
        ) : (
        <Stack spacing={2}>
          <Typography variant="body2">{t('system.debug_export.intro')}</Typography>

          <Box>
            <Typography variant="subtitle2" gutterBottom>
              {t('system.debug_export.preset_label')}
            </Typography>
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
              {(['minimal', 'recommended', 'full'] as Preset[]).map((value) => (
                <ActionButton
                  key={value}
                  actionType={preset === value ? 'primary' : 'secondary'}
                  size="small"
                  onClick={() => applyPreset(value)}
                  disabled={busy}
                >
                  {t(`system.debug_export.preset_${value}`)}
                </ActionButton>
              ))}
            </Stack>
          </Box>

          <Divider />

          <Box>
            <Typography variant="subtitle2" gutterBottom>
              {t('system.debug_export.selection_label')}
            </Typography>
            {renderBlock('system', true)}
            {renderBlock('logs', selection.logs, (value) => update('logs', value))}
            {renderBlock('settings', selection.settings, (value) => update('settings', value))}
            {renderBlock('network', selection.network, (value) => update('network', value))}
            {renderBlock(
              'media',
              selection.media !== 'off',
              (value) => update('media', value ? 'counts' : 'off'),
              selection.media !== 'off' ? (
                <Box>
                  <Typography variant="caption" color="text.secondary" display="block" gutterBottom>
                    {t('system.debug_export.media_level')}
                  </Typography>
                  <Select
                    size="small"
                    value={selection.media}
                    onChange={(event) =>
                      update('media', event.target.value as DebugExportMediaLevel)
                    }
                  >
                    <MenuItem value="counts">{t('system.debug_export.media_counts')}</MenuItem>
                    <MenuItem value="filenames" disabled={!elevated}>
                      {t('system.debug_export.media_filenames')}
                    </MenuItem>
                  </Select>
                </Box>
              ) : undefined
            )}
            {renderBlock('history', selection.history, (value) => update('history', value))}
            {renderBlock('client', selection.client, (value) => update('client', value))}
            {renderBlock(
              'include_db',
              selection.include_db,
              (value) => {
                update('include_db', value);
                if (!value) setDbConfirmed(false);
              },
              selection.include_db ? (
                <FormControlLabel
                  control={
                    <Checkbox
                      checked={dbConfirmed}
                      onChange={(event) => setDbConfirmed(event.target.checked)}
                    />
                  }
                  label={
                    <Typography variant="caption">
                      {t('system.debug_export.blocks.database.confirm')}
                    </Typography>
                  }
                />
              ) : undefined
            )}
          </Box>

          <Alert severity="info" icon={false}>
            <Typography variant="subtitle2" gutterBottom>
              {t('system.debug_export.privacy_title')}
            </Typography>
            <Stack spacing={0.75}>
              <Typography variant="caption">{t('system.debug_export.privacy_storage')}</Typography>
              <Typography variant="caption">{t('system.debug_export.privacy_removed')}</Typography>
              <Typography variant="caption">{t('system.debug_export.privacy_never')}</Typography>
              <Typography variant="caption">{t('system.debug_export.privacy_maybe')}</Typography>
              <Typography variant="caption">{t('system.debug_export.privacy_check')}</Typography>
            </Stack>
          </Alert>

          {error && <Alert severity="error">{error}</Alert>}
          {done && <Alert severity="success">{t('system.debug_export.created')}</Alert>}
          {busy && (
            <Typography variant="caption" color="text.secondary">
              {t('system.debug_export.duration_hint')}
            </Typography>
          )}
        </Stack>
        )}
      </DialogContent>
      <DialogActions>
        {preview ? (
          <>
            <ActionButton
              actionType="secondary"
              onClick={() => setPreview(null)}
              disabled={busy}
            >
              {t('system.debug_export.preview_back')}
            </ActionButton>
            <ActionButton
              actionType="primary"
              onClick={handlePreviewDownload}
              loading={busy}
              disabled={busy}
            >
              {t('system.debug_export.preview_download')}
            </ActionButton>
          </>
        ) : (
          <>
            <ActionButton actionType="secondary" onClick={onClose} disabled={busy}>
              {t('actions.close', { ns: 'common' })}
            </ActionButton>
            <ActionButton actionType="secondary" onClick={handlePreview} disabled={busy}>
              {t('system.debug_export.preview')}
            </ActionButton>
            <ActionButton
              actionType="primary"
              onClick={handleCreate}
              loading={busy}
              disabled={busy}
            >
              {busy ? t('system.debug_export.creating') : t('system.debug_export.create')}
            </ActionButton>
          </>
        )}
      </DialogActions>
    </ResponsiveDialog>
  );
};
