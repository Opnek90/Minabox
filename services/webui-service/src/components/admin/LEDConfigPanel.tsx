import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardActions,
  CardContent,
  CardHeader,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  Divider,
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
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/Delete';
import EditIcon from '@mui/icons-material/Edit';
import ElectricBoltIcon from '@mui/icons-material/ElectricBolt';
import SaveIcon from '@mui/icons-material/Save';
import ToggleOnIcon from '@mui/icons-material/ToggleOn';
import ToggleOffIcon from '@mui/icons-material/ToggleOff';
import { useTranslation } from 'react-i18next';
import { useToast } from '@/contexts/ToastContext';
import { configApi } from '@/api/config';
import type { LEDConfig, LED, LEDPattern, LEDPatternType } from '@/types/api';
import { useLayout } from '@/hooks/useLayout';


export const LEDConfigPanel: React.FC = () => {
  const { t } = useTranslation('admin');
  const { showSuccess, showError } = useToast();
  const isSmall = useLayout().isMobile;

  const [config, setConfig] = useState<LEDConfig | null>(null);
  const [ledStates, setLedStates] = useState<string[]>([]);
  const [ledPatterns, setLedPatterns] = useState<LEDPatternType[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [testingLedId, setTestingLedId] = useState<string | null>(null);

  const [editLed, setEditLed] = useState<LED | null>(null);
  const [isNewLed, setIsNewLed] = useState(false);
  const [activeStep, setActiveStep] = useState(0);
  const [ledForm, setLedForm] = useState({ id: '', name: '', gpio: 17 });
  const [bindingsForm, setBindingsForm] = useState<Record<string, LEDPattern>>({});
  const [addBindingState, setAddBindingState] = useState('');
  const [deleteLed, setDeleteLed] = useState<LED | null>(null);

  const stepLabels = useMemo(
    () => [t('leds.steps.basics'), t('leds.steps.bindings')],
    [t]
  );

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
      showSuccess(t('leds.save_success'));
    } catch {
      showError(t('leds.save_error'));
    } finally {
      setSaving(false);
    }
  };

  const handleToggleEnabled = (led: LED) => {
    setConfig((prev) =>
      prev
        ? {
            leds: prev.leds.map((l) =>
              l.id === led.id ? { ...l, enabled: !(l.enabled ?? true) } : l
            ),
          }
        : prev
    );
  };

  const openAddLed = () => {
    const nextNum = config?.leds.length
      ? Math.max(...config.leds.map((l) => parseInt(l.id.replace(/\D/g, ''), 10) || 0)) + 1
      : 1;
    // No duration_ms for solid — the solid pattern stays on indefinitely (bug #97)
    setLedForm({ id: `led_${nextNum}`, name: '', gpio: 17 });
    setBindingsForm({ system_online: { pattern_type: 'solid' } });
    setEditLed({ id: `led_${nextNum}`, name: '', gpio: 17, bindings: {}, enabled: true });
    setIsNewLed(true);
    setActiveStep(0);
  };

  const openEditLed = (led: LED) => {
    setLedForm({ id: led.id, name: led.name, gpio: led.gpio });
    setBindingsForm({ ...led.bindings });
    setEditLed(led);
    setIsNewLed(false);
    setActiveStep(0);
  };

  const closeDialog = () => {
    setEditLed(null);
    setActiveStep(0);
  };

  const handleNext = () => setActiveStep((s) => s + 1);
  const handleBack = () => setActiveStep((s) => s - 1);
  const isStep0Valid = ledForm.name.trim().length > 0 && ledForm.id.trim().length > 0;

  const updateBinding = (state: string, patch: Partial<LEDPattern>) => {
    setBindingsForm((prev) => ({
      ...prev,
      [state]: { ...(prev[state] || { pattern_type: 'solid' }), ...patch },
    }));
  };

  const addBinding = (state: string) => {
    setBindingsForm((prev) => ({
      ...prev,
      [state]: { pattern_type: 'solid' },
    }));
    setAddBindingState('');
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
    const updatedLed: LED = {
      id: ledForm.id,
      name: ledForm.name,
      gpio: ledForm.gpio,
      bindings: bindingsForm,
      enabled: editLed.enabled ?? true,
    };
    if (isNewLed) {
      setConfig({ leds: [...config.leds, updatedLed] });
    } else {
      setConfig({ leds: config.leds.map((l) => (l.id === ledForm.id ? updatedLed : l)) });
    }
    closeDialog();
  };

  const handleDeleteLed = (led: LED) => {
    setConfig((prev) => prev ? { leds: prev.leds.filter((l) => l.id !== led.id) } : prev);
    setDeleteLed(null);
  };

  const handleTestLed = async (led: LED) => {
    setTestingLedId(led.id);
    try {
      await configApi.testLed(led.id);
      showSuccess(t('leds.test_success', { name: led.name }));
    } catch {
      showError(t('leds.test_error', { name: led.name }));
    } finally {
      setTestingLedId(null);
    }
  };

  if (!config) {
    return error ? <Alert severity="error">{error}</Alert> : null;
  }

  const availableStates = ledStates.filter((s) => !(s in bindingsForm));

  // ── Shared action buttons renderer ────────────────────────────────────
  const renderLedActions = (led: LED) => {
    const isEnabled = led.enabled ?? true;
    return (
      <Stack direction="row" spacing={0.5}>
        <Tooltip title={isEnabled ? t('leds.disable_led') : t('leds.enable_led')}>
          <IconButton size="small" color={isEnabled ? 'success' : 'default'} onClick={() => handleToggleEnabled(led)}>
            {isEnabled ? <ToggleOnIcon fontSize="small" /> : <ToggleOffIcon fontSize="small" />}
          </IconButton>
        </Tooltip>
        <Tooltip title={t('leds.test_led')}>
          <span>
            <IconButton
              size="small"
              color="warning"
              disabled={testingLedId !== null || !isEnabled}
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
    );
  };

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
      ) : isSmall ? (
        // ── Mobile: Card list ──────────────────────────────────────────
        <Stack spacing={1.5}>
          {config.leds.map((led) => {
            const isEnabled = led.enabled ?? true;
            const bindingCount = Object.keys(led.bindings).length;
            return (
              <Card
                key={led.id}
                variant="outlined"
                sx={{ opacity: isEnabled ? 1 : 0.5 }}
              >
                <CardContent sx={{ pb: 0 }}>
                  <Box display="flex" justifyContent="space-between" alignItems="flex-start">
                    <Box>
                      <Typography variant="subtitle2" fontWeight={700}>
                        {led.name}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {led.id}
                      </Typography>
                    </Box>
                  </Box>
                  <Stack direction="row" spacing={0.75} flexWrap="wrap" mt={1} useFlexGap>
                    <Chip label={`GPIO ${led.gpio}`} size="small" variant="outlined" />
                    {bindingCount > 0 && (
                      <Chip
                        label={`${bindingCount} ${t('leds.fields.bindings')}`}
                        size="small"
                        variant="outlined"
                        color="primary"
                      />
                    )}
                  </Stack>
                </CardContent>
                <CardActions sx={{ pt: 0.5, px: 1.5 }}>
                  {renderLedActions(led)}
                </CardActions>
              </Card>
            );
          })}
        </Stack>
      ) : (
        // ── Desktop: Table ─────────────────────────────────────────────
        <TableContainer component={Paper} variant="outlined">
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell sx={{ fontWeight: 700 }}>{t('leds.fields.name')}</TableCell>
                <TableCell sx={{ fontWeight: 700 }}>GPIO</TableCell>
                <TableCell sx={{ fontWeight: 700 }}>{t('leds.fields.bindings')}</TableCell>
                <TableCell align="right" sx={{ fontWeight: 700 }}>{t('leds.fields.actions')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {config.leds.map((led) => {
                const isEnabled = led.enabled ?? true;
                return (
                  <TableRow key={led.id} hover sx={{ opacity: isEnabled ? 1 : 0.45 }}>
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
                        {renderLedActions(led)}
                      </Stack>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      {/* ── Edit / Add Dialog ─────────────────────────────────────────── */}
      <Dialog open={!!editLed} onClose={closeDialog} maxWidth="sm" fullWidth fullScreen={isSmall}>
        <DialogTitle>
          {isNewLed ? t('leds.add_led') : t('leds.edit_led')}
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
                label={t('leds.fields.id')} value={ledForm.id}
                onChange={(e) => setLedForm((p) => ({ ...p, id: e.target.value }))}
                size="small" fullWidth disabled={!isNewLed}
                helperText={t('leds.fields.id_hint')}
              />
              <TextField
                label={t('leds.fields.name')} value={ledForm.name}
                onChange={(e) => setLedForm((p) => ({ ...p, name: e.target.value }))}
                size="small" fullWidth required autoFocus={isNewLed}
              />
              <TextField
                label={t('leds.fields.gpio')} type="number" value={ledForm.gpio}
                onChange={(e) => setLedForm((p) => ({ ...p, gpio: parseInt(e.target.value, 10) || 0 }))}
                size="small" fullWidth inputProps={{ min: 0 }}
                helperText={t('leds.fields.gpio_hint')}
              />
            </Stack>
          )}

          {activeStep === 1 && (
            <Box>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                {t('leds.bindings.description')}
              </Typography>
              <Stack spacing={1.5} sx={{ mb: 2 }}>
                {Object.entries(bindingsForm).length === 0 && (
                  <Typography variant="body2" color="text.disabled">
                    {t('leds.bindings.none')}
                  </Typography>
                )}
                {Object.entries(bindingsForm).map(([state, pat]) => (
                  <Card key={state} variant="outlined">
                    <CardHeader
                      title={<Typography variant="subtitle2" fontWeight={700}>{state}</Typography>}
                      action={
                        <IconButton size="small" color="error" onClick={() => removeBinding(state)}>
                          <DeleteIcon fontSize="small" />
                        </IconButton>
                      }
                      sx={{ pb: 0, pt: 1, px: 2 }}
                    />
                    <Divider />
                    <CardContent
                      sx={{
                        pt: 1.5,
                        display: 'grid',
                        gridTemplateColumns: isSmall ? '1fr' : '1fr 1fr',
                        gap: 1.5,
                        '&:last-child': { pb: 1.5 },
                      }}
                    >
                      {/* Pattern type dropdown */}
                      <TextField
                        select label={t('leds.bindings.pattern')}
                        value={pat.pattern_type || 'solid'}
                        onChange={(e) => updateBinding(state, { pattern_type: e.target.value as LEDPattern['pattern_type'] })}
                        size="small" fullWidth
                        SelectProps={{ native: true }} InputLabelProps={{ shrink: true }}
                      >
                        {ledPatterns.map((p) => (
                          <option key={p} value={p}>{t(`leds.bindings.patterns.${p}` as const)}</option>
                        ))}
                      </TextField>

                      {/* duration_ms: only for 'pulse' */}
                      {(pat.pattern_type === 'pulse') && (
                        <TextField
                          label={t('leds.bindings.duration_ms')} type="number"
                          value={pat.duration_ms ?? ''}
                          onChange={(e) => updateBinding(state, { duration_ms: e.target.value ? parseInt(e.target.value, 10) : undefined })}
                          size="small" fullWidth inputProps={{ min: 0 }}
                        />
                      )}

                      {/* interval_ms: only for 'blink' */}
                      {(pat.pattern_type === 'blink') && (
                        <TextField
                          label={t('leds.bindings.interval_ms')} type="number"
                          value={pat.interval_ms ?? ''}
                          onChange={(e) => updateBinding(state, { interval_ms: e.target.value ? parseInt(e.target.value, 10) : undefined })}
                          size="small" fullWidth inputProps={{ min: 50 }}
                        />
                      )}

                      {/* cycle_ms: only for 'glow' */}
                      {(pat.pattern_type === 'glow') && (
                        <TextField
                          label={t('leds.bindings.cycle_ms')} type="number"
                          value={pat.cycle_ms ?? 2000}
                          onChange={(e) => updateBinding(state, { cycle_ms: e.target.value ? parseInt(e.target.value, 10) : 2000 })}
                          size="small" fullWidth inputProps={{ min: 500 }}
                          helperText={t('leds.bindings.cycle_ms_hint')}
                        />
                      )}

                      {/* min_brightness: only for 'glow' */}
                      {(pat.pattern_type === 'glow') && (
                        <TextField
                          label={t('leds.bindings.min_brightness')} type="number"
                          value={pat.min_brightness ?? 0.0}
                          onChange={(e) => updateBinding(state, { min_brightness: e.target.value !== '' ? parseFloat(e.target.value) : 0.0 })}
                          size="small" fullWidth inputProps={{ min: 0, max: 1, step: 0.1 }}
                        />
                      )}

                      {/* max_brightness: only for 'glow' */}
                      {(pat.pattern_type === 'glow') && (
                        <TextField
                          label={t('leds.bindings.max_brightness')} type="number"
                          value={pat.max_brightness ?? 1.0}
                          onChange={(e) => updateBinding(state, { max_brightness: e.target.value !== '' ? parseFloat(e.target.value) : 1.0 })}
                          size="small" fullWidth inputProps={{ min: 0, max: 1, step: 0.1 }}
                        />
                      )}

                      {/* repeat: for blink, pulse, glow */}
                      {(pat.pattern_type !== 'solid' && pat.pattern_type !== 'off') && (
                        <TextField
                          label={t('leds.bindings.repeat')} type="number"
                          value={pat.repeat ?? ''}
                          onChange={(e) => updateBinding(state, { repeat: e.target.value ? parseInt(e.target.value, 10) : undefined })}
                          size="small" fullWidth inputProps={{ min: 0 }} placeholder="0"
                          helperText={t('leds.bindings.repeat_hint')}
                        />
                      )}
                    </CardContent>
                  </Card>
                ))}
              </Stack>

              {availableStates.length > 0 && (
                <TextField
                  select size="small" label={t('leds.bindings.add')}
                  value={addBindingState}
                  onChange={(e) => { if (e.target.value) addBinding(e.target.value); }}
                  fullWidth SelectProps={{ native: true }} InputLabelProps={{ shrink: true }}
                >
                  <option value="">— {t('leds.bindings.add_placeholder')}</option>
                  {availableStates.map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </TextField>
              )}
            </Box>
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
              <Button variant="contained" onClick={handleSaveLedDialog} disabled={!isStep0Valid}>
                {t('save', { ns: 'common' })}
              </Button>
            )}
          </Box>
        </DialogActions>
      </Dialog>

      {/* ── Delete Dialog ─────────────────────────────────────────────── */}
      <Dialog open={!!deleteLed} onClose={() => setDeleteLed(null)}>
        <DialogTitle>{t('leds.delete_led')}</DialogTitle>
        <DialogContent>
          <DialogContentText>
            {t('leds.delete_confirm', { name: deleteLed?.name })}
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteLed(null)}>{t('cancel', { ns: 'common' })}</Button>
          <Button onClick={() => deleteLed && handleDeleteLed(deleteLed)} color="error" variant="contained">
            {t('delete', { ns: 'common' })}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};
