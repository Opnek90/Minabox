import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  IconButton,
  Paper,
  Stack,
  Step,
  StepLabel,
  Stepper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography,
  useMediaQuery,
  useTheme,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/Delete';
import EditIcon from '@mui/icons-material/Edit';
import ScienceIcon from '@mui/icons-material/Science';
import SaveIcon from '@mui/icons-material/Save';
import { useTranslation } from 'react-i18next';
import { useToast } from '@/contexts/ToastContext';
import { configApi } from '@/api/config';
import { useWebSocketEvent } from '@/contexts/WebSocketContext';
import type { ButtonConfig, Button as ButtonType, ButtonRawEventMessage } from '@/types/api';


export const ButtonConfigPanel: React.FC = () => {
  const { t } = useTranslation('admin');
  const { showSuccess, showError } = useToast();
  const theme = useTheme();
  const isSmall = useMediaQuery(theme.breakpoints.down('sm'));

  const [config, setConfig] = useState<ButtonConfig | null>(null);
  const [buttonActions, setButtonActions] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [editBtn, setEditBtn] = useState<ButtonType | null>(null);
  const [isNewBtn, setIsNewBtn] = useState(false);
  const [activeStep, setActiveStep] = useState(0);
  const [btnForm, setBtnForm] = useState<Partial<ButtonType>>({
    id: '', name: '', mode: 'basic', type: 'push',
    gpio: undefined, clk: undefined, dt: undefined, sw: undefined,
  });

  const [deleteBtn, setDeleteBtn] = useState<ButtonType | null>(null);
  const [testBtn, setTestBtn] = useState<ButtonType | null>(null);
  const [btnEvents, setBtnEvents] = useState<string[]>([]);
  const eventsEndRef = useRef<HTMLDivElement>(null);

  // Keep a ref so the WebSocket callback always sees the latest testBtn
  // without needing to re-register the listener on every state change.
  const testBtnRef = useRef<ButtonType | null>(null);
  testBtnRef.current = testBtn;

  const stepLabels = useMemo(
    () => [t('buttons.steps.basics'), t('buttons.steps.actions')],
    [t]
  );

  useEffect(() => {
    configApi.getButtons().then(setConfig).catch(() => setError('Laden fehlgeschlagen'));
    configApi.getButtonActions().then(setButtonActions).catch(() => {});
  }, []);

  // Listen for raw button events from the hardware test-mode.
  // `button_raw_event` is emitted by the backend for every physical press,
  // regardless of whether an action mapping exists.
  useWebSocketEvent(
    'button_raw_event',
    useCallback((msg: ButtonRawEventMessage) => {
      if (!testBtnRef.current) return;
      const data = msg.data;
      const ts = data.timestamp ? new Date(data.timestamp).toLocaleTimeString() : '';
      const label = data.name ?? data.button_id ?? '?';
      const evType = data.event_type ?? '?';
      setBtnEvents((prev) => [`[${ts}] ${label}: ${evType}`, ...prev]);
    }, []),
  );

  useEffect(() => {
    eventsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [btnEvents]);

  const handleSave = async () => {
    if (!config) return;
    setSaving(true);
    try {
      const updated = await configApi.updateButtons(config);
      setConfig(updated);
      showSuccess(t('buttons.save_success'));
    } catch {
      showError(t('buttons.save_error', { defaultValue: 'Speichern fehlgeschlagen' }));
    } finally {
      setSaving(false);
    }
  };

  const openAddButton = () => {
    const nextId = config?.buttons.length
      ? `btn_${config.buttons.length + 1}`
      : 'btn_1';
    setBtnForm({ id: nextId, name: '', mode: 'basic', type: 'push', gpio: undefined });
    setEditBtn({ id: nextId, name: '', mode: 'basic', type: 'push', gpio: undefined });
    setIsNewBtn(true);
    setActiveStep(0);
  };

  const openEditButton = (btn: ButtonType) => {
    setBtnForm({ ...btn });
    setEditBtn(btn);
    setIsNewBtn(false);
    setActiveStep(0);
  };

  const closeDialog = () => {
    setEditBtn(null);
    setActiveStep(0);
  };

  const handleNext = () => setActiveStep((s) => s + 1);
  const handleBack = () => setActiveStep((s) => s - 1);

  const isStep0Valid =
    (btnForm.name ?? '').trim().length > 0 &&
    (btnForm.id ?? '').trim().length > 0;

  const handleSaveButtonDialog = () => {
    if (!editBtn || !config) return;
    const mode = (btnForm.mode as ButtonType['mode']) ?? editBtn.mode;
    const rawActions = btnForm.actions ?? editBtn.actions ?? null;
    const actionsClean =
      mode === 'advanced' && rawActions
        ? Object.fromEntries(
            Object.entries(rawActions).filter(
              ([, v]) => v != null && String(v).trim() !== ''
            )
          )
        : null;
    const updated: ButtonType = {
      id: btnForm.id ?? editBtn.id,
      name: btnForm.name ?? editBtn.name,
      mode,
      type: (btnForm.type as ButtonType['type']) ?? editBtn.type,
      gpio: btnForm.gpio ?? editBtn.gpio ?? null,
      clk: btnForm.clk ?? editBtn.clk ?? null,
      dt: btnForm.dt ?? editBtn.dt ?? null,
      sw: btnForm.sw ?? editBtn.sw ?? null,
      ...(mode === 'basic'
        ? { action: btnForm.action ?? editBtn.action ?? null, actions: null }
        : {
            actions:
              Object.keys(actionsClean ?? {}).length ? actionsClean : null,
          }),
    };
    if (isNewBtn) {
      setConfig({ buttons: [...config.buttons, updated] });
    } else {
      setConfig({
        buttons: config.buttons.map((b) => (b.id === editBtn.id ? updated : b)),
      });
    }
    closeDialog();
  };

  const handleDeleteBtn = (btn: ButtonType) => {
    setConfig((prev) =>
      prev ? { buttons: prev.buttons.filter((b) => b.id !== btn.id) } : prev
    );
    setDeleteBtn(null);
  };

  if (!config) {
    return error ? <Alert severity="error">{error}</Alert> : null;
  }

  const advancedEvents =
    btnForm.type === 'rotary'
      ? ['rotate_cw', 'rotate_ccw', 'press']
      : ['short_press', 'long_press', 'double_press'];

  return (
    <Box>
      <Box display="flex" alignItems="center" gap={2} mb={2}>
        <Button variant="outlined" startIcon={<AddIcon />} onClick={openAddButton}>
          {t('buttons.add_button')}
        </Button>
        <Button
          variant="contained"
          startIcon={<SaveIcon />}
          onClick={handleSave}
          disabled={saving}
        >
          {t('save', { ns: 'common' })}
        </Button>
      </Box>

      {config.buttons.length === 0 ? (
        <Typography color="text.secondary">{t('buttons.no_buttons')}</Typography>
      ) : (
        <TableContainer component={Paper} variant="outlined">
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell sx={{ fontWeight: 700 }}>{t('buttons.fields.name')}</TableCell>
                <TableCell sx={{ fontWeight: 700 }}>{t('buttons.fields.type')}</TableCell>
                <TableCell sx={{ fontWeight: 700 }}>GPIO</TableCell>
                <TableCell sx={{ fontWeight: 700 }}>{t('buttons.fields.mode')}</TableCell>
                <TableCell align="right" sx={{ fontWeight: 700 }}>
                  {t('buttons.fields.actions')}
                </TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {config.buttons.map((btn) => (
                <TableRow key={btn.id} hover>
                  <TableCell>
                    <Typography variant="body2" fontWeight={600}>{btn.name}</Typography>
                    <Typography variant="caption" color="text.secondary">{btn.id}</Typography>
                  </TableCell>
                  <TableCell>
                    <Chip label={t(`buttons.types.${btn.type}`)} size="small" variant="outlined" />
                  </TableCell>
                  <TableCell>
                    {btn.type === 'rotary' ? (
                      <Stack direction="row" spacing={0.5} flexWrap="wrap">
                        {btn.clk != null && <Chip label={`CLK ${btn.clk}`} size="small" variant="outlined" />}
                        {btn.dt != null && <Chip label={`DT ${btn.dt}`} size="small" variant="outlined" />}
                        {btn.sw != null && <Chip label={`SW ${btn.sw}`} size="small" variant="outlined" />}
                      </Stack>
                    ) : btn.gpio != null ? (
                      <Chip label={`GPIO ${btn.gpio}`} size="small" variant="outlined" />
                    ) : (
                      <Typography variant="caption" color="text.disabled">–</Typography>
                    )}
                  </TableCell>
                  <TableCell>
                    <Chip
                      label={t(`buttons.modes.${btn.mode}`).split(' ')[0]}
                      size="small"
                      color={btn.mode === 'advanced' ? 'primary' : 'default'}
                      variant="outlined"
                    />
                  </TableCell>
                  <TableCell align="right">
                    <Stack direction="row" spacing={0.5} justifyContent="flex-end">
                      <Tooltip title={t('buttons.test_button')}>
                        <IconButton
                          size="small"
                          color="info"
                          onClick={() => { setBtnEvents([]); setTestBtn(btn); }}
                        >
                          <ScienceIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                      <Tooltip title={t('buttons.edit_button')}>
                        <IconButton size="small" onClick={() => openEditButton(btn)}>
                          <EditIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                      <Tooltip title={t('buttons.delete_button')}>
                        <IconButton size="small" color="error" onClick={() => setDeleteBtn(btn)}>
                          <DeleteIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                    </Stack>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}

      {/* ── Edit / Add Dialog ─────────────────────────────────────────── */}
      <Dialog open={!!editBtn} onClose={closeDialog} maxWidth="sm" fullWidth fullScreen={isSmall}>
        <DialogTitle>
          {isNewBtn ? t('buttons.add_button') : t('buttons.edit_button')}
        </DialogTitle>
        <DialogContent>
          <Stepper activeStep={activeStep} sx={{ mb: 3 }}>
            {stepLabels.map((label) => (
              <Step key={label}><StepLabel>{label}</StepLabel></Step>
            ))}
          </Stepper>

          {activeStep === 0 && (
            <Stack spacing={2}>
              <TextField
                label={t('buttons.fields.id')}
                value={btnForm.id ?? ''}
                onChange={(e) => setBtnForm((p) => ({ ...p, id: e.target.value }))}
                size="small" fullWidth disabled={!isNewBtn}
                helperText={t('buttons.fields.id_hint')}
              />
              <TextField
                label={t('buttons.fields.name')}
                value={btnForm.name ?? ''}
                onChange={(e) => setBtnForm((p) => ({ ...p, name: e.target.value }))}
                size="small" fullWidth required autoFocus={isNewBtn}
              />
              <TextField
                select label={t('buttons.fields.type')}
                value={btnForm.type ?? 'push'}
                onChange={(e) => setBtnForm((p) => ({ ...p, type: e.target.value as ButtonType['type'] }))}
                size="small" fullWidth
                SelectProps={{ native: true }} InputLabelProps={{ shrink: true }}
              >
                <option value="push">{t('buttons.types.push')}</option>
                <option value="rotary">{t('buttons.types.rotary')}</option>
              </TextField>
              <TextField
                select label={t('buttons.fields.mode')}
                value={btnForm.mode ?? 'basic'}
                onChange={(e) => setBtnForm((p) => ({ ...p, mode: e.target.value as ButtonType['mode'] }))}
                size="small" fullWidth
                SelectProps={{ native: true }} InputLabelProps={{ shrink: true }}
                helperText={t('buttons.fields.mode_hint')}
              >
                <option value="basic">{t('buttons.modes.basic')}</option>
                <option value="advanced">{t('buttons.modes.advanced')}</option>
              </TextField>

              {(btnForm.type ?? 'push') === 'push' ? (
                <TextField
                  label={t('buttons.fields.gpio')} type="number"
                  value={btnForm.gpio ?? ''}
                  onChange={(e) => setBtnForm((p) => ({ ...p, gpio: e.target.value ? parseInt(e.target.value, 10) : undefined }))}
                  size="small" fullWidth inputProps={{ min: 0 }}
                  helperText={t('buttons.fields.gpio_hint')}
                />
              ) : (
                <Stack direction="row" spacing={1.5}>
                  {(['clk', 'dt', 'sw'] as const).map((pin) => (
                    <TextField
                      key={pin} label={pin.toUpperCase()} type="number"
                      value={btnForm[pin] ?? ''}
                      onChange={(e) => setBtnForm((p) => ({ ...p, [pin]: e.target.value ? parseInt(e.target.value, 10) : undefined }))}
                      size="small" fullWidth inputProps={{ min: 0 }}
                    />
                  ))}
                </Stack>
              )}
            </Stack>
          )}

          {activeStep === 1 && (
            <Stack spacing={2}>
              <Typography variant="body2" color="text.secondary">
                {(btnForm.mode ?? 'basic') === 'basic'
                  ? t('buttons.actions.basic_hint')
                  : t('buttons.actions.advanced_hint')}
              </Typography>
              {(btnForm.mode ?? 'basic') === 'basic' ? (
                <TextField
                  select label={t('buttons.actions.action')}
                  value={btnForm.action ?? ''}
                  onChange={(e) => setBtnForm((p) => ({ ...p, action: e.target.value || null }))}
                  size="small" fullWidth
                  SelectProps={{ native: true }} InputLabelProps={{ shrink: true }}
                >
                  <option value="">—</option>
                  {buttonActions.map((a) => (
                    <option key={a} value={a}>{a.replace(/_/g, ' ')}</option>
                  ))}
                </TextField>
              ) : (
                <Stack spacing={1.5}>
                  {advancedEvents.map((ev) => (
                    <TextField
                      key={ev} select
                      label={t(`buttons.actions.events.${ev}`)}
                      value={btnForm.actions?.[ev] ?? ''}
                      onChange={(e) => setBtnForm((p) => ({ ...p, actions: { ...(p.actions || {}), [ev]: e.target.value || '' } }))}
                      size="small" fullWidth
                      SelectProps={{ native: true }} InputLabelProps={{ shrink: true }}
                    >
                      <option value="">—</option>
                      {buttonActions.map((a) => (
                        <option key={a} value={a}>{a.replace(/_/g, ' ')}</option>
                      ))}
                    </TextField>
                  ))}
                </Stack>
              )}
            </Stack>
          )}
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2, justifyContent: 'space-between' }}>
          <Button onClick={closeDialog}>{t('cancel', { ns: 'common' })}</Button>
          <Box display="flex" gap={1}>
            {activeStep > 0 && (
              <Button onClick={handleBack}>{t('back', { ns: 'common' })}</Button>
            )}
            {activeStep < stepLabels.length - 1 ? (
              <Button variant="contained" onClick={handleNext} disabled={!isStep0Valid}>
                {t('next', { ns: 'common' })}
              </Button>
            ) : (
              <Button variant="contained" onClick={handleSaveButtonDialog} disabled={!isStep0Valid}>
                {t('save', { ns: 'common' })}
              </Button>
            )}
          </Box>
        </DialogActions>
      </Dialog>

      {/* ── Test Modal ────────────────────────────────────────────────── */}
      <Dialog open={!!testBtn} onClose={() => setTestBtn(null)} maxWidth="sm" fullWidth>
        <DialogTitle>
          {t('buttons.test_modal.title')} – {testBtn?.name}
        </DialogTitle>
        <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <Typography variant="body2" color="text.secondary">
            {t('buttons.test_modal.description')}
          </Typography>
          <Paper
            variant="outlined"
            sx={{ height: 200, overflowY: 'auto', p: 1.5, bgcolor: 'background.default', fontFamily: 'monospace' }}
          >
            {btnEvents.length === 0 ? (
              <Typography variant="caption" color="text.disabled">
                {t('buttons.test_modal.no_events')}
              </Typography>
            ) : (
              btnEvents.map((ev, i) => (
                <Typography key={i} variant="caption" display="block" sx={{ lineHeight: 1.8 }}>
                  {ev}
                </Typography>
              ))
            )}
            <div ref={eventsEndRef} />
          </Paper>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setBtnEvents([])}>{t('clear', { ns: 'common' })}</Button>
          <Button variant="contained" onClick={() => setTestBtn(null)}>
            {t('buttons.test_modal.close')}
          </Button>
        </DialogActions>
      </Dialog>

      {/* ── Delete Dialog ─────────────────────────────────────────────── */}
      <Dialog open={!!deleteBtn} onClose={() => setDeleteBtn(null)}>
        <DialogTitle>{t('buttons.delete_button')}</DialogTitle>
        <DialogContent>
          <DialogContentText>
            {t('buttons.delete_confirm', { name: deleteBtn?.name })}
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteBtn(null)}>{t('cancel', { ns: 'common' })}</Button>
          <Button onClick={() => deleteBtn && handleDeleteBtn(deleteBtn)} color="error" variant="contained">
            {t('delete', { ns: 'common' })}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};
