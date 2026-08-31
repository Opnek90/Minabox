import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Divider,
  Stack,
  Typography,
} from '@mui/material';
import LightbulbIcon from '@mui/icons-material/Lightbulb';
import TouchAppIcon from '@mui/icons-material/TouchApp';
import MonitorIcon from '@mui/icons-material/Monitor';
import { useTranslation } from 'react-i18next';
import { configApi } from '@/api/config';
import { systemApi } from '@/api/system';
import { useWebSocketEvent } from '@/contexts/WebSocketContext';
import { isServiceUp } from '@/types/api';
import type { ButtonRawEventMessage, LEDConfig } from '@/types/api';

export const HardwareStep: React.FC = () => {
  const { t } = useTranslation('setup');
  const [running, setRunning] = useState<Set<string>>(new Set());
  const [leds, setLeds] = useState<LEDConfig['leds']>([]);
  const [presses, setPresses] = useState<string[]>([]);
  const [displayResult, setDisplayResult] = useState<'idle' | 'ok' | 'fail'>('idle');
  const [ledError, setLedError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    systemApi
      .getStatus()
      .then((s) =>
        setRunning(
          new Set(s.services.filter((x) => isServiceUp(x.state)).map((x) => x.service)),
        ),
      )
      .catch(() => setRunning(new Set()))
      .finally(() => setLoading(false));

    configApi
      .getLeds()
      .then((c) => setLeds(c.leds ?? []))
      .catch(() => setLeds([]));
  }, []);

  // Every physical button press lands here, including buttons with no action
  // mapping - that is exactly why the button handler sends the raw event.
  useWebSocketEvent(
    'button_raw_event',
    useCallback((msg: ButtonRawEventMessage) => {
      const label = msg.data.name ?? msg.data.button_id ?? '?';
      setPresses((prev) => [label, ...prev].slice(0, 5));
    }, []),
  );

  const testLed = async (id: string) => {
    setLedError(null);
    try {
      await configApi.testLed(id);
    } catch {
      setLedError(t('hardware.test_failed'));
    }
  };

  const testDisplay = async () => {
    setDisplayResult('idle');
    try {
      await configApi.testDisplay();
      setDisplayResult('ok');
    } catch {
      setDisplayResult('fail');
    }
  };

  if (loading) return <CircularProgress size={24} />;

  const hasLed = running.has('led');
  const hasButton = running.has('button');
  const hasDisplay = running.has('display');

  if (!hasLed && !hasButton && !hasDisplay) {
    return (
      <Stack spacing={2}>
        <Typography variant="h6">{t('hardware.heading')}</Typography>
        <Alert severity="info">{t('hardware.none')}</Alert>
      </Stack>
    );
  }

  return (
    <Stack spacing={2}>
      <Typography variant="h6">{t('hardware.heading')}</Typography>
      <Typography variant="body2" color="text.secondary">
        {t('hardware.intro')}
      </Typography>

      {hasLed && (
        <Box>
          <Typography variant="subtitle2" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <LightbulbIcon fontSize="small" /> {t('hardware.leds')}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {t('hardware.led_hint')}
          </Typography>
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mt: 1 }}>
            {leds.map((led) => (
              <Button key={led.id} size="small" variant="outlined" onClick={() => testLed(led.id)}>
                {led.name || led.id}
              </Button>
            ))}
          </Stack>
          {ledError && (
            <Alert severity="error" sx={{ mt: 1 }}>
              {ledError}
            </Alert>
          )}
        </Box>
      )}

      {hasLed && hasButton && <Divider />}

      {hasButton && (
        <Box>
          <Typography variant="subtitle2" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <TouchAppIcon fontSize="small" /> {t('hardware.buttons')}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {t('hardware.buttons_hint')}
          </Typography>
          <Box sx={{ mt: 1 }}>
            {presses.length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                {t('hardware.buttons_waiting')}
              </Typography>
            ) : (
              <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                {presses.map((p, i) => (
                  <Chip
                    key={`${p}-${i}`}
                    label={t('hardware.buttons_detected', { name: p })}
                    color={i === 0 ? 'success' : 'default'}
                    size="small"
                  />
                ))}
              </Stack>
            )}
          </Box>
        </Box>
      )}

      {hasButton && hasDisplay && <Divider />}

      {hasDisplay && (
        <Box>
          <Typography variant="subtitle2" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <MonitorIcon fontSize="small" /> {t('hardware.display')}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {t('hardware.display_hint')}
          </Typography>
          <Box sx={{ mt: 1 }}>
            <Button size="small" variant="outlined" onClick={testDisplay}>
              {t('hardware.display_test')}
            </Button>
          </Box>
          {displayResult === 'fail' && (
            <Alert severity="error" sx={{ mt: 1 }}>
              {t('hardware.test_failed')}
            </Alert>
          )}
        </Box>
      )}
    </Stack>
  );
};
