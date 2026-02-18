import React, { useEffect, useRef, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  IconButton,
  Paper,
  Snackbar,
  Stack,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tabs,
  TextField,
  Tooltip,
  Typography,
  useMediaQuery,
  useTheme,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/Delete';
import EditIcon from '@mui/icons-material/Edit';
import ElectricBoltIcon from '@mui/icons-material/ElectricBolt';
import ScienceIcon from '@mui/icons-material/Science';
import SaveIcon from '@mui/icons-material/Save';
import { useTranslation } from 'react-i18next';
import { SystemStatusPanel } from '@/components/admin/SystemStatus';
import {
  AudioConfigForm,
  DesignSettingsForm,
  GeneralSettingsForm,
  RFIDConfigForm,
} from '@/components/admin/ConfigForm';
import { configApi } from '@/api/config';
import { useWebSocket } from '@/contexts/WebSocketContext';
import type { LEDConfig, LED, LEDPattern, ButtonConfig, Button as ButtonType } from '@/types/api';


interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}

const TabPanel: React.FC<TabPanelProps> = ({ children, value, index }) => (
  <Box role="tabpanel" hidden={value !== index} sx={{ pt: 3 }}>
    {value === index && children}
  </Box>
);

// ============================================================================
// LED Config Panel
// ============================================================================
const LEDConfigPanel: React.FC = () => {
  const { t } = useTranslation('admin');
  const [config, setConfig] = useState<LEDConfig | null>(null);
  const [ledStates, setLedStates] = useState<string[]>([]);
  const [ledPatterns, setLedPatterns] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deleteLed, setDeleteLed] = useState<LED | null>(null);
  const [editLed, setEditLed] = useState<LED | null>(null);
  const [ledForm, setLedForm] = useState({ id: '', name: '', gpio: 17 });
  const [bindingsForm, setBindingsForm] = useState<Record<string, LEDPattern>>({});
  const [addBindingState, setAddBindingState] = useState('');

  useEffect(() => {
    configApi.getLeds().then(setConfig).catch(() => setError('Laden fehlgeschlagen'));
    configApi.getLedStates().then(setLedStates).catch(() => {});
    configApi.getLedPatterns().then(setLedPatterns).catch(() => {});
  }, []);

  const handleSave = async () => {
    if (!config) return;
    setSaving(true);
    try {
      const updated = await configApi.updateLeds(config);
      setConfig(updated);
      setSuccess(true);
    } catch {
      setError('Speichern fehlgeschlagen');
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteLed = (led: LED) => {
    setConfig((prev) =>
      prev ? { leds: prev.leds.filter((l) => l.id !== led.id) } : prev
    );
    setDeleteLed(null);
  };

  const openAddLed = () => {
    const nextNum = config?.leds.length ? Math.max(...config.leds.map((l) => parseInt(l.id.replace(/\D/g, ''), 10) || 0)) + 1 : 1;
    setLedForm({ id: `led_${nextNum}`, name: '', gpio: 17 });
    setBindingsForm({ system_online: { pattern_type: 'solid', duration_ms: 0 } });
    setEditLed({ id: `led_${nextNum}`, name: '', gpio: 17, bindings: {} });
  };

  const openEditLed = (led: LED) => {
    setLedForm({ id: led.id, name: led.name, gpio: led.gpio });
    setBindingsForm({ ...led.bindings });
    setEditLed(led);
  };

  const updateBinding = (state: string, patch: Partial<LEDPattern>) => {
    setBindingsForm((prev) => ({
      ...prev,
      [state]: { ...(prev[state] || { pattern_type: 'solid' }), ...patch },
    }));
  };

  const addBinding = (state: string) => {
    setBindingsForm((prev) => ({ ...prev, [state]: { pattern_type: 'solid', duration_ms: 0 } }));
  };

  const removeBinding = (state: string) => {
    setBindingsForm((prev) => {
      const next = { ...prev };
      delete next[state];
      return next;
    });
  };

  const handleSaveLedDialog = () => {
    if (!editLed || !config) return;
    const isNew = !config.leds.some((l) => l.id === ledForm.id);
    const updatedLed: LED = {
      id: ledForm.id,
      name: ledForm.name,
      gpio: ledForm.gpio,
      bindings: bindingsForm,
    };
    if (isNew) {
      setConfig({ leds: [...config.leds, updatedLed] });
    } else {
      setConfig({ leds: config.leds.map((l) => (l.id === ledForm.id ? updatedLed : l)) });
    }
    setEditLed(null);
  };

  const [testingLedId, setTestingLedId] = useState<string | null>(null);
  const [testError, setTestError] = useState<string | null>(null);

  const handleTestLed = async (led: LED) => {
    setTestingLedId(led.id);
    setTestError(null);
    try {
      await configApi.testLed(led.id);
      setSuccess(true);
    } catch {
      setTestError(`${t('leds.test_led')}: ${led.name}`);
    } finally {
      setTestingLedId(null);
    }
  };

  if (!config) {
    return error ? <Alert severity="error">{error}</Alert> : null;
  }

  return (
    <Box>
      <Box display="flex" alignItems="center" gap={2} mb={2}>
        <Button variant="outlined" startIcon={<AddIcon />} onClick={openAddLed}>
          {t('leds.add_led')}
        </Button>
        <Button variant="contained" startIcon={<SaveIcon />} onClick={handleSave} disabled={saving}>
          {t('save', { ns: 'common' })}
        </Button>
      </Box>

      {config.leds.length === 0 ? (
        <Typography color="text.secondary">{t('leds.no_leds')}</Typography>
      ) : (
        <TableContainer component={Paper} variant="outlined">
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell sx={{ fontWeight: 700 }}>{t('leds.fields.name')}</TableCell>
                <TableCell sx={{ fontWeight: 700 }}>GPIO</TableCell>
                <TableCell sx={{ fontWeight: 700 }}>{t('leds.fields.bindings')}</TableCell>
                <TableCell align="right" sx={{ fontWeight: 700 }}>{t('leds.fields.actions', { defaultValue: 'Aktionen' })}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {config.leds.map((led) => (
                <TableRow key={led.id} hover>
                  <TableCell>
                    <Typography variant="body2" fontWeight={600}>{led.name}</Typography>
                    <Typography variant="caption" color="text.secondary">{led.id}</Typography>
                  </TableCell>
                  <TableCell>
                    <Chip label={`GPIO ${led.gpio}`} size="small" variant="outlined" />
                  </TableCell>
                  <TableCell>
                    <Box display="flex" flexWrap="wrap" gap={0.5}>
                      {Object.entries(led.bindings).map(([state, pat]) => (
                        <Chip
                          key={state}
                          label={`${state} → ${pat.pattern_type}`}
                          size="small"
                          sx={{ fontSize: '0.7rem' }}
                        />
                      ))}
                      {Object.keys(led.bindings).length === 0 && (
                        <Typography variant="caption" color="text.disabled">–</Typography>
                      )}
                    </Box>
                  </TableCell>
                  <TableCell align="right">
                    <Stack direction="row" spacing={0.5} justifyContent="flex-end">
                      <Tooltip title={t('leds.test_led')}>
                        <span>
                          <IconButton
                            size="small"
                            color="warning"
                            disabled={testingLedId !== null || Object.keys(led.bindings).length === 0}
                            onClick={() => handleTestLed(led)}
                          >
                            {testingLedId === led.id ? (
                              <CircularProgress size={16} color="warning" />
                            ) : (
                              <ElectricBoltIcon fontSize="small" />
                            )}
                          </IconButton>
                        </span>
                      </Tooltip>
                      <Tooltip title={t('leds.edit_led')}>
                        <IconButton size="small" onClick={() => openEditLed(led)}>
                          <EditIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                      <Tooltip title={t('leds.delete_led')}>
                        <IconButton size="small" color="error" onClick={() => setDeleteLed(led)}>
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

      {(error || testError) && (
        <Alert severity="error" sx={{ mt: 2 }}>{testError ?? error}</Alert>
      )}

      <Dialog open={!!editLed} onClose={() => setEditLed(null)} maxWidth="md" fullWidth>
        <DialogTitle sx={{ fontSize: '1.25rem', fontWeight: 600, pb: 1 }}>
          {editLed && config?.leds.some((l) => l.id === editLed.id) ? t('leds.edit_led') : t('leds.add_led')}
        </DialogTitle>
        <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 3, pt: '16px !important' }}>
          <Box display="flex" flexWrap="wrap" gap={2} sx={{ pt: 1 }}>
            <TextField
              label={t('leds.fields.id')}
              value={ledForm.id}
              onChange={(e) => setLedForm((p) => ({ ...p, id: e.target.value }))}
              size="small"
              sx={{ minWidth: 180 }}
              disabled={!!editLed && config.leds.some((l) => l.id === editLed.id)}
            />
            <TextField
              label={t('leds.fields.name')}
              value={ledForm.name}
              onChange={(e) => setLedForm((p) => ({ ...p, name: e.target.value }))}
              size="small"
              sx={{ flex: 1, minWidth: 200 }}
            />
            <TextField
              label={t('leds.fields.gpio')}
              type="number"
              value={ledForm.gpio}
              onChange={(e) => setLedForm((p) => ({ ...p, gpio: parseInt(e.target.value, 10) || 0 }))}
              size="small"
              sx={{ minWidth: 140 }}
              inputProps={{ min: 0 }}
            />
          </Box>
          <Typography variant="subtitle2" color="text.secondary" sx={{ fontWeight: 600 }}>{t('leds.bindings.title')}</Typography>
          {Object.entries(bindingsForm).map(([state, pat]) => (
            <Box
              key={state}
              display="flex"
              flexWrap="wrap"
              alignItems="flex-start"
              gap={2}
              sx={{ p: 2, pt: 3, bgcolor: 'action.hover', borderRadius: 1 }}
            >
              <Typography variant="body2" fontWeight={600} sx={{ minWidth: 140, pt: 1 }}>{state}</Typography>
              <TextField
                select
                label={t('leds.bindings.pattern')}
                value={pat.pattern_type || 'solid'}
                onChange={(e) => updateBinding(state, { pattern_type: e.target.value as LEDPattern['pattern_type'] })}
                size="small"
                sx={{ minWidth: 160 }}
                SelectProps={{ native: true }}
              >
                {ledPatterns.map((p) => (
                  <option key={p} value={p}>{t(`leds.bindings.patterns.${p}`, { defaultValue: p })}</option>
                ))}
              </TextField>
              <TextField
                label={t('leds.bindings.duration_ms')}
                type="number"
                value={pat.duration_ms ?? ''}
                onChange={(e) => updateBinding(state, { duration_ms: e.target.value ? parseInt(e.target.value, 10) : undefined })}
                size="small"
                sx={{ minWidth: 150 }}
                inputProps={{ min: 0 }}
              />
              {(pat.pattern_type || 'solid') === 'blink' && (
                <TextField
                  label={t('leds.bindings.interval_ms')}
                  type="number"
                  value={pat.interval_ms ?? ''}
                  onChange={(e) => updateBinding(state, { interval_ms: e.target.value ? parseInt(e.target.value, 10) : undefined })}
                  size="small"
                  sx={{ minWidth: 150 }}
                  inputProps={{ min: 50 }}
                />
              )}
              <TextField
                label={t('leds.bindings.repeat')}
                type="number"
                value={pat.repeat ?? ''}
                onChange={(e) => updateBinding(state, { repeat: e.target.value ? parseInt(e.target.value, 10) : undefined })}
                size="small"
                sx={{ minWidth: 180 }}
                inputProps={{ min: 0 }}
                placeholder="0"
              />
              <IconButton size="small" color="error" onClick={() => removeBinding(state)} sx={{ mt: 0.5 }}>
                <DeleteIcon fontSize="small" />
              </IconButton>
            </Box>
          ))}
          <Box display="flex" alignItems="center" gap={2} flexWrap="wrap">
            <TextField
              select
              size="small"
              label={t('leds.bindings.add')}
              value={addBindingState}
              onChange={(e) => { const v = e.target.value; if (v) { addBinding(v); setAddBindingState(''); } }}
              sx={{ minWidth: 240 }}
              SelectProps={{ native: true }}
            >
              <option value="">—</option>
              {ledStates.filter((s) => !(s in bindingsForm)).map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </TextField>
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditLed(null)}>{t('cancel', { ns: 'common' })}</Button>
          <Button variant="contained" onClick={handleSaveLedDialog}>
            {t('save', { ns: 'common' })}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={!!deleteLed} onClose={() => setDeleteLed(null)}>
        <DialogTitle sx={{ fontSize: '1.25rem', fontWeight: 600 }}>{t('leds.delete_led')}</DialogTitle>
        <DialogContent>
          <DialogContentText>
            {t('leds.delete_confirm', { name: deleteLed?.name })}
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteLed(null)}>{t('cancel', { ns: 'common' })}</Button>
          <Button
            onClick={() => deleteLed && handleDeleteLed(deleteLed)}
            color="error"
            variant="contained"
          >
            {t('delete', { ns: 'common' })}
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar open={success} autoHideDuration={3000} onClose={() => setSuccess(false)} message={t('leds.save_success')} />
    </Box>
  );
};

// ============================================================================
// Button Config Panel
// ============================================================================
const ButtonConfigPanel: React.FC = () => {
  const { t } = useTranslation('admin');
  const [config, setConfig] = useState<ButtonConfig | null>(null);
  const [buttonActions, setButtonActions] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deleteBtn, setDeleteBtn] = useState<ButtonType | null>(null);
  const [editBtn, setEditBtn] = useState<ButtonType | null>(null);
  const [btnForm, setBtnForm] = useState<Partial<ButtonType>>({ id: '', name: '', mode: 'basic', type: 'push', gpio: undefined, clk: undefined, dt: undefined, sw: undefined });

  useEffect(() => {
    configApi.getButtons().then(setConfig).catch(() => setError('Laden fehlgeschlagen'));
    configApi.getButtonActions().then(setButtonActions).catch(() => {});
  }, []);

  const handleSave = async () => {
    if (!config) return;
    setSaving(true);
    try {
      const updated = await configApi.updateButtons(config);
      setConfig(updated);
      setSuccess(true);
    } catch {
      setError('Speichern fehlgeschlagen');
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteBtn = (btn: ButtonType) => {
    setConfig((prev) =>
      prev ? { buttons: prev.buttons.filter((b) => b.id !== btn.id) } : prev
    );
    setDeleteBtn(null);
  };

  const openAddButton = () => {
    const nextId = config?.buttons.length ? `btn_${config.buttons.length + 1}` : 'btn_1';
    setBtnForm({ id: nextId, name: '', mode: 'basic', type: 'push', gpio: undefined });
    setEditBtn({ id: nextId, name: '', mode: 'basic', type: 'push', gpio: undefined });
  };

  const openEditButton = (btn: ButtonType) => {
    setBtnForm({ ...btn });
    setEditBtn(btn);
  };

  const handleSaveButtonDialog = () => {
    if (!editBtn || !config) return;
    const isNew = !config.buttons.some((b) => b.id === btnForm.id);
    const updated: ButtonType = {
      id: (btnForm.id ?? editBtn.id),
      name: btnForm.name ?? editBtn.name,
      mode: (btnForm.mode as ButtonType['mode']) ?? editBtn.mode,
      type: (btnForm.type as ButtonType['type']) ?? editBtn.type,
      gpio: btnForm.gpio ?? editBtn.gpio ?? null,
      clk: btnForm.clk ?? editBtn.clk ?? null,
      dt: btnForm.dt ?? editBtn.dt ?? null,
      sw: btnForm.sw ?? editBtn.sw ?? null,
      action: btnForm.action ?? editBtn.action ?? null,
      actions: btnForm.actions ?? editBtn.actions ?? null,
    };
    if (isNew) {
      setConfig({ buttons: [...config.buttons, updated] });
    } else {
      setConfig({ buttons: config.buttons.map((b) => (b.id === editBtn.id ? updated : b)) });
    }
    setEditBtn(null);
  };

  const [testBtn, setTestBtn] = useState<ButtonType | null>(null);
  const { lastMessage } = useWebSocket();
  const [btnEvents, setBtnEvents] = useState<string[]>([]);
  const eventsEndRef = useRef<HTMLDivElement>(null);

  // Accumulate button_action events while the test modal is open
  useEffect(() => {
    if (!testBtn) return;
    if (lastMessage?.type === 'button_action') {
      const data = lastMessage.data as { action?: string; timestamp?: string };
      const ts = data.timestamp ? new Date(data.timestamp).toLocaleTimeString() : '';
      setBtnEvents((prev) => [`[${ts}] action: ${data.action ?? '?'}`, ...prev]);
    }
  }, [lastMessage, testBtn]);

  // Auto-scroll log to top (newest first)
  useEffect(() => {
    eventsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [btnEvents]);

  const openButtonTestModal = (btn: ButtonType) => {
    setBtnEvents([]);
    setTestBtn(btn);
  };

  if (!config) {
    return error ? <Alert severity="error">{error}</Alert> : null;
  }

  return (
    <Box>
      <Box display="flex" alignItems="center" gap={2} mb={2}>
        <Button variant="outlined" startIcon={<AddIcon />} onClick={openAddButton}>
          {t('buttons.add_button')}
        </Button>
        <Button variant="contained" startIcon={<SaveIcon />} onClick={handleSave} disabled={saving}>
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
                <TableCell align="right" sx={{ fontWeight: 700 }}>{t('buttons.fields.actions', { defaultValue: 'Aktionen' })}</TableCell>
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
                    ) : (
                      btn.gpio != null
                        ? <Chip label={`GPIO ${btn.gpio}`} size="small" variant="outlined" />
                        : <Typography variant="caption" color="text.disabled">–</Typography>
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
                        <IconButton size="small" color="info" onClick={() => openButtonTestModal(btn)}>
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

      {/* Button Test Modal */}
      <Dialog open={!!testBtn} onClose={() => setTestBtn(null)} maxWidth="sm" fullWidth>
        <DialogTitle sx={{ fontWeight: 700 }}>
          {t('buttons.test_modal.title')} – {testBtn?.name}
        </DialogTitle>
        <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <Typography variant="body2" color="text.secondary">
            {t('buttons.test_modal.description')}
          </Typography>
          <Paper
            variant="outlined"
            sx={{
              height: 200,
              overflowY: 'auto',
              p: 1.5,
              bgcolor: 'background.default',
              fontFamily: 'monospace',
            }}
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
          <Button onClick={() => { setBtnEvents([]); }}>{t('clear', { ns: 'common', defaultValue: 'Clear' })}</Button>
          <Button variant="contained" onClick={() => setTestBtn(null)}>
            {t('buttons.test_modal.close')}
          </Button>
        </DialogActions>
      </Dialog>

      {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}

      <Dialog open={!!editBtn} onClose={() => setEditBtn(null)} maxWidth="md" fullWidth>
        <DialogTitle sx={{ fontSize: '1.25rem', fontWeight: 600, pb: 1 }}>
          {editBtn && config.buttons.some((b) => b.id === editBtn.id) ? t('buttons.edit_button') : t('buttons.add_button')}
        </DialogTitle>
        <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 3, pt: '16px !important' }}>
          <Box display="flex" flexWrap="wrap" gap={2} sx={{ pt: 1 }}>
            <TextField
              label={t('buttons.fields.id')}
              value={btnForm.id ?? ''}
              onChange={(e) => setBtnForm((p) => ({ ...p, id: e.target.value }))}
              size="small"
              sx={{ minWidth: 180 }}
              disabled={!!editBtn && config.buttons.some((b) => b.id === editBtn.id)}
            />
            <TextField
              label={t('buttons.fields.name')}
              value={btnForm.name ?? ''}
              onChange={(e) => setBtnForm((p) => ({ ...p, name: e.target.value }))}
              size="small"
              sx={{ flex: 1, minWidth: 200 }}
            />
            <TextField
              select
              label={t('buttons.fields.type')}
              value={btnForm.type ?? 'push'}
              onChange={(e) => setBtnForm((p) => ({ ...p, type: e.target.value as ButtonType['type'] }))}
              size="small"
              sx={{ minWidth: 160 }}
              SelectProps={{ native: true }}
            >
              <option value="push">{t('buttons.types.push')}</option>
              <option value="rotary">{t('buttons.types.rotary')}</option>
            </TextField>
            <TextField
              select
              label={t('buttons.fields.mode')}
              value={btnForm.mode ?? 'basic'}
              onChange={(e) => setBtnForm((p) => ({ ...p, mode: e.target.value as ButtonType['mode'] }))}
              size="small"
              sx={{ minWidth: 180 }}
              SelectProps={{ native: true }}
            >
              <option value="basic">{t('buttons.modes.basic')}</option>
              <option value="advanced">{t('buttons.modes.advanced')}</option>
            </TextField>
          </Box>
          {(btnForm.type ?? 'push') === 'push' ? (
            <TextField
              label={t('buttons.fields.gpio')}
              type="number"
              value={btnForm.gpio ?? ''}
              onChange={(e) => setBtnForm((p) => ({ ...p, gpio: e.target.value ? parseInt(e.target.value, 10) : undefined }))}
              size="small"
              sx={{ minWidth: 140 }}
              inputProps={{ min: 0 }}
            />
          ) : (
            <Box display="flex" gap={2} flexWrap="wrap">
              <TextField label="CLK" type="number" value={btnForm.clk ?? ''} onChange={(e) => setBtnForm((p) => ({ ...p, clk: e.target.value ? parseInt(e.target.value, 10) : undefined }))} size="small" sx={{ minWidth: 100 }} inputProps={{ min: 0 }} />
              <TextField label="DT" type="number" value={btnForm.dt ?? ''} onChange={(e) => setBtnForm((p) => ({ ...p, dt: e.target.value ? parseInt(e.target.value, 10) : undefined }))} size="small" sx={{ minWidth: 100 }} inputProps={{ min: 0 }} />
              <TextField label="SW" type="number" value={btnForm.sw ?? ''} onChange={(e) => setBtnForm((p) => ({ ...p, sw: e.target.value ? parseInt(e.target.value, 10) : undefined }))} size="small" sx={{ minWidth: 100 }} inputProps={{ min: 0 }} />
            </Box>
          )}
          <Typography variant="subtitle2" color="text.secondary" sx={{ fontWeight: 600 }}>{t('buttons.actions.title')}</Typography>
          {(btnForm.mode ?? 'basic') === 'basic' ? (
            <TextField
              select
              label={t('buttons.actions.action')}
              value={btnForm.action ?? ''}
              onChange={(e) => setBtnForm((p) => ({ ...p, action: e.target.value || null }))}
              size="small"
              sx={{ minWidth: 220 }}
              SelectProps={{ native: true }}
            >
              <option value="">—</option>
              {buttonActions.map((a) => (
                <option key={a} value={a}>{a.replace(/_/g, ' ')}</option>
              ))}
            </TextField>
          ) : (
            <Box display="flex" flexDirection="column" gap={1.5}>
              {(btnForm.type === 'rotary' ? ['rotate_cw', 'rotate_ccw', 'press'] : ['short_press', 'long_press', 'double_press']).map((ev) => (
                <Box key={ev} display="flex" alignItems="center" gap={2} flexWrap="wrap">
                  <Typography variant="body2" sx={{ minWidth: 160 }}>{t(`buttons.actions.events.${ev}`)}</Typography>
                  <TextField
                    select
                    size="small"
                    value={btnForm.actions?.[ev] ?? ''}
                    onChange={(e) => setBtnForm((p) => ({
                      ...p,
                      actions: { ...(p.actions || {}), [ev]: e.target.value || '' },
                    }))}
                    sx={{ minWidth: 200 }}
                    SelectProps={{ native: true }}
                  >
                    <option value="">—</option>
                    {buttonActions.map((a) => (
                      <option key={a} value={a}>{a.replace(/_/g, ' ')}</option>
                    ))}
                  </TextField>
                </Box>
              ))}
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditBtn(null)}>{t('cancel', { ns: 'common' })}</Button>
          <Button variant="contained" onClick={handleSaveButtonDialog}>
            {t('save', { ns: 'common' })}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={!!deleteBtn} onClose={() => setDeleteBtn(null)}>
        <DialogTitle sx={{ fontSize: '1.25rem', fontWeight: 600 }}>{t('buttons.delete_button')}</DialogTitle>
        <DialogContent>
          <DialogContentText>
            {t('buttons.delete_confirm', { name: deleteBtn?.name })}
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteBtn(null)}>{t('cancel', { ns: 'common' })}</Button>
          <Button
            onClick={() => deleteBtn && handleDeleteBtn(deleteBtn)}
            color="error"
            variant="contained"
          >
            {t('delete', { ns: 'common' })}
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar open={success} autoHideDuration={3000} onClose={() => setSuccess(false)} message={t('buttons.save_success')} />
    </Box>
  );
};

// ============================================================================
// Admin Page
// ============================================================================

export const AdminPage: React.FC = () => {
  const { t } = useTranslation('admin');
  const theme = useTheme();
  const isSmall = useMediaQuery(theme.breakpoints.down('sm'));
  const [tab, setTab] = useState(0);

  return (
    <Box sx={{ p: isSmall ? 1.5 : 3 }}>
      <Typography variant="h5" fontWeight={700} gutterBottom sx={{ fontSize: isSmall ? '1.25rem' : undefined }}>
        {t('title')}
      </Typography>

      <Tabs
        value={tab}
        onChange={(_, v) => setTab(v)}
        variant="scrollable"
        scrollButtons="auto"
        allowScrollButtonsMobile
        visibleScrollbar
        sx={{
          borderBottom: 1,
          borderColor: 'divider',
          minHeight: 48,
          '& .MuiTabs-flexContainer': { gap: 0 },
          '& .MuiTabs-scroller': { overflowX: 'auto', WebkitOverflowScrolling: 'touch' },
          ...(isSmall && {
            '& .MuiTab-root': { minHeight: 40, py: 0.5, fontSize: '0.8rem' },
          }),
        }}
      >
        <Tab label={t('tabs.system')} />
        <Tab label={t('tabs.general')} />
        <Tab label={t('tabs.design')} />
        <Tab label={t('tabs.audio')} />
        <Tab label={t('tabs.leds')} />
        <Tab label={t('tabs.buttons')} />
        <Tab label={t('tabs.rfid')} />
      </Tabs>

      <TabPanel value={tab} index={0}>
        <SystemStatusPanel />
      </TabPanel>

      <TabPanel value={tab} index={1}>
        <Typography variant="h6" gutterBottom>{t('general.title')}</Typography>
        <GeneralSettingsForm />
      </TabPanel>

      <TabPanel value={tab} index={2}>
        <Typography variant="h6" gutterBottom>{t('design.title')}</Typography>
        <DesignSettingsForm />
      </TabPanel>

      <TabPanel value={tab} index={3}>
        <Typography variant="h6" gutterBottom>{t('audio.title')}</Typography>
        <AudioConfigForm />
      </TabPanel>

      <TabPanel value={tab} index={4}>
        <Typography variant="h6" gutterBottom>{t('leds.title')}</Typography>
        <LEDConfigPanel />
      </TabPanel>

      <TabPanel value={tab} index={5}>
        <Typography variant="h6" gutterBottom>{t('buttons.title')}</Typography>
        <ButtonConfigPanel />
      </TabPanel>

      <TabPanel value={tab} index={6}>
        <Typography variant="h6" gutterBottom>{t('rfid.title')}</Typography>
        <RFIDConfigForm />
      </TabPanel>
    </Box>
  );
};
