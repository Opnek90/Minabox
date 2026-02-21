import React, { useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  FormControl,
  IconButton,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Switch,
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
import ArrowDownwardIcon from '@mui/icons-material/ArrowDownward';
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward';
import SaveIcon from '@mui/icons-material/Save';
import { useTranslation } from 'react-i18next';
import { useToast } from '@/contexts/ToastContext';
import { configApi } from '@/api/config';
import type {
  DisplayConfig,
  DisplayElement,
  DisplayElementType,
  DisplayArea,
  DisplayFontSize,
  DisplayFont,
} from '@/types/api';

function mergeElements(
  existing: DisplayElement[],
  types: string[]
): DisplayElement[] {
  const byType = new Map(existing.map((e) => [e.type, e]));
  return types.map((type, index) => {
    const el = byType.get(type as DisplayElementType);
    if (el) {
      return { ...el, order: el.order, area: el.area ?? 0 };
    }
    return {
      id: type,
      type: type as DisplayElementType,
      enabled: false,
      order: index,
      area: 0 as DisplayArea,
    };
  });
}

function sortByOrder(elements: DisplayElement[]): DisplayElement[] {
  return [...elements].sort((a, b) => a.order - b.order);
}

export const DisplayConfigPanel: React.FC = () => {
  const { t } = useTranslation('admin');
  const { showSuccess, showError } = useToast();
  const [config, setConfig] = useState<DisplayConfig | null>(null);
  const [elementTypes, setElementTypes] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    configApi
      .getDisplay()
      .then((data) => {
        setConfig(data);
      })
      .catch(() => setError('Laden fehlgeschlagen'));
    configApi.getDisplayElementTypes().then(setElementTypes).catch(() => {});
  }, []);

  useEffect(() => {
    if (config && elementTypes.length > 0) {
      const merged = mergeElements(config.elements, elementTypes);
      const sorted = sortByOrder(merged);
      setConfig((prev) => (prev ? { ...prev, elements: sorted } : prev));
    }
  }, [elementTypes.length]);

  const handleSave = async () => {
    if (!config) return;
    setSaving(true);
    try {
      const updated = await configApi.updateDisplay(config);
      setConfig(updated);
      showSuccess(t('display.save_success'));
    } catch {
      showError(t('display.save_error'));
    } finally {
      setSaving(false);
    }
  };

  const setEnabled = (global: boolean) => {
    setConfig((prev) => (prev ? { ...prev, enabled: global } : prev));
  };

  const setElementEnabled = (type: DisplayElementType, enabled: boolean) => {
    setConfig((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        elements: prev.elements.map((e) =>
          e.type === type ? { ...e, enabled } : e
        ),
      };
    });
  };

  const moveElement = (type: DisplayElementType, direction: 'up' | 'down') => {
    setConfig((prev) => {
      if (!prev) return prev;
      const sorted = sortByOrder(prev.elements);
      const idx = sorted.findIndex((e) => e.type === type);
      if (idx < 0) return prev;
      const newIdx = direction === 'up' ? idx - 1 : idx + 1;
      if (newIdx < 0 || newIdx >= sorted.length) return prev;
      const reordered = [...sorted];
      const [removed] = reordered.splice(idx, 1);
      reordered.splice(newIdx, 0, removed);
      const withOrder = reordered.map((e, i) => ({ ...e, order: i }));
      return { ...prev, elements: withOrder };
    });
  };

  const setI2cBus = (value: number) => {
    setConfig((prev) => (prev ? { ...prev, i2c_bus: value } : prev));
  };

  const setI2cAddress = (value: number) => {
    setConfig((prev) => (prev ? { ...prev, i2c_address: value } : prev));
  };

  const setFontSize = (value: DisplayFontSize) => {
    setConfig((prev) => (prev ? { ...prev, font_size: value } : prev));
  };

  const setFont = (value: DisplayFont) => {
    setConfig((prev) => (prev ? { ...prev, font: value } : prev));
  };

  const setElementArea = (type: DisplayElementType, area: DisplayArea) => {
    setConfig((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        elements: prev.elements.map((e) =>
          e.type === type ? { ...e, area } : e
        ),
      };
    });
  };

  if (!config) {
    return error ? <Alert severity="error">{error}</Alert> : null;
  }

  const sortedElements = sortByOrder(config.elements);

  return (
    <Box>
      <Paper sx={{ p: 2, mb: 2 }}>
        <Box display="flex" alignItems="center" justifyContent="space-between" flexWrap="wrap" gap={2}>
          <Box display="flex" alignItems="center" gap={2}>
            <Typography variant="subtitle1" fontWeight={600}>
              {t('display.enabled')}
            </Typography>
            <Switch
              checked={config.enabled}
              onChange={(_, checked) => setEnabled(checked)}
              color="primary"
            />
          </Box>
          <Box display="flex" gap={1} alignItems="center">
            <TextField
              label={t('display.i2c_bus')}
              type="number"
              size="small"
              value={config.i2c_bus}
              onChange={(e) => setI2cBus(parseInt(e.target.value, 10) || 1)}
              inputProps={{ min: 0, max: 9 }}
              sx={{ width: 90 }}
            />
            <TextField
              label={t('display.i2c_address')}
              type="number"
              size="small"
              value={config.i2c_address}
              onChange={(e) => setI2cAddress(parseInt(e.target.value, 10) || 60)}
              inputProps={{ min: 0, max: 127 }}
              sx={{ width: 100 }}
            />
            <FormControl size="small" sx={{ minWidth: 120 }}>
              <InputLabel>{t('display.font_size')}</InputLabel>
              <Select
                label={t('display.font_size')}
                value={config.font_size ?? 'medium'}
                onChange={(e) => setFontSize(e.target.value as DisplayFontSize)}
              >
                <MenuItem value="small">{t('display.font_size_small')}</MenuItem>
                <MenuItem value="medium">{t('display.font_size_medium')}</MenuItem>
                <MenuItem value="large">{t('display.font_size_large')}</MenuItem>
              </Select>
            </FormControl>
            <FormControl size="small" sx={{ minWidth: 120 }}>
              <InputLabel>{t('display.font')}</InputLabel>
              <Select
                label={t('display.font')}
                value={config.font ?? 'default'}
                onChange={(e) => setFont(e.target.value as DisplayFont)}
              >
                <MenuItem value="default">{t('display.font_default')}</MenuItem>
                <MenuItem value="sans">{t('display.font_sans')}</MenuItem>
                <MenuItem value="mono">{t('display.font_mono')}</MenuItem>
              </Select>
            </FormControl>
          </Box>
        </Box>
      </Paper>

      <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1 }}>
        {t('display.elements')}
      </Typography>
      <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
        {t('display.elements_hint')}
      </Typography>
      <TableContainer component={Paper} sx={{ mb: 2 }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>{t('display.order')}</TableCell>
              <TableCell>#</TableCell>
              <TableCell align="left">{t('display.elements')}</TableCell>
              <TableCell align="left">{t('display.area')}</TableCell>
              <TableCell align="left">{t('display.active')}</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {sortedElements.map((el, index) => (
              <TableRow key={el.type}>
                <TableCell>
                  <Box display="flex" alignItems="center" gap={0.5}>
                    <Tooltip title={t('display.order') + ' hoch'}>
                      <IconButton
                        size="small"
                        disabled={index === 0}
                        onClick={() => moveElement(el.type, 'up')}
                      >
                        <ArrowUpwardIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                    <Tooltip title={t('display.order') + ' runter'}>
                      <IconButton
                        size="small"
                        disabled={index === sortedElements.length - 1}
                        onClick={() => moveElement(el.type, 'down')}
                      >
                        <ArrowDownwardIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  </Box>
                </TableCell>
                <TableCell>{index + 1}</TableCell>
                <TableCell>
                  {t(`display.element_types.${el.type}` as const)}
                </TableCell>
                <TableCell>
                  <Box display="flex" gap={0.5}>
                    {([0, 1, 2] as DisplayArea[]).map((a) => (
                      <Button
                        key={a}
                        size="small"
                        variant={(el.area ?? 0) === a ? 'contained' : 'outlined'}
                        onClick={() => setElementArea(el.type, a)}
                        sx={{ minWidth: 56 }}
                      >
                        {a === 0
                          ? t('display.area_header')
                          : a === 1
                            ? t('display.area_left')
                            : t('display.area_right')}
                      </Button>
                    ))}
                  </Box>
                </TableCell>
                <TableCell>
                  <Switch
                    size="small"
                    checked={el.enabled}
                    onChange={(_, checked) => setElementEnabled(el.type, checked)}
                    color="primary"
                  />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>

      <Button
        variant="contained"
        startIcon={<SaveIcon />}
        onClick={handleSave}
        disabled={saving}
      >
        {saving ? '…' : t('display.save_button', { defaultValue: 'Speichern' })}
      </Button>
    </Box>
  );
};
