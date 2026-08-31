import React, { useCallback, useEffect, useState } from 'react';
import { Alert, Box, Button, Divider, Stack, Typography } from '@mui/material';
import NfcIcon from '@mui/icons-material/Nfc';
import LibraryMusicIcon from '@mui/icons-material/LibraryMusic';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { tagsApi } from '@/api/tags';
import { systemApi } from '@/api/system';
import { useWebSocketEvent } from '@/contexts/WebSocketContext';
import { isServiceUp } from '@/types/api';
import type { RFIDScannedMessage } from '@/types/api';

export const ContentStep: React.FC = () => {
  const { t } = useTranslation('setup');
  const navigate = useNavigate();
  const [learning, setLearning] = useState(false);
  const [tagId, setTagId] = useState<string | null>(null);
  const [rfidRunning, setRfidRunning] = useState(true);

  useEffect(() => {
    systemApi
      .getStatus()
      .then((s) =>
        setRfidRunning(s.services.some((x) => x.service === 'rfid' && isServiceUp(x.state))),
      )
      .catch(() => setRfidRunning(false));
  }, []);

  // Learn mode must also be turned off again when the user leaves the step -
  // otherwise the box stays stuck in learn mode and plays nothing.
  useEffect(() => {
    return () => {
      if (learning) void tagsApi.setLearningMode(false).catch(() => {});
    };
  }, [learning]);

  useWebSocketEvent(
    'rfid_scanned_learning',
    useCallback(
      (msg: RFIDScannedMessage) => {
        setTagId(msg.data.tag_id);
        setLearning(false);
        void tagsApi.setLearningMode(false).catch(() => {});
      },
      [],
    ),
  );

  const start = async () => {
    setTagId(null);
    try {
      await tagsApi.setLearningMode(true);
      setLearning(true);
    } catch {
      setRfidRunning(false);
    }
  };

  const stop = async () => {
    setLearning(false);
    await tagsApi.setLearningMode(false).catch(() => {});
  };

  return (
    <Stack spacing={2}>
      <Typography variant="h6">{t('content.heading')}</Typography>
      <Typography variant="body2" color="text.secondary">
        {t('content.intro')}
      </Typography>

      <Box>
        <Typography variant="subtitle2" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <NfcIcon fontSize="small" /> {t('content.card')}
        </Typography>

        {!rfidRunning ? (
          <Alert severity="info" sx={{ mt: 1 }}>
            {t('content.card_unavailable')}
          </Alert>
        ) : (
          <Box sx={{ mt: 1 }}>
            {!learning && (
              <Button size="small" variant="outlined" onClick={start}>
                {t('content.card_start')}
              </Button>
            )}
            {learning && (
              <Stack spacing={1}>
                <Typography variant="body2">{t('content.card_waiting')}</Typography>
                <Box>
                  <Button size="small" onClick={stop}>
                    {t('content.card_stop')}
                  </Button>
                </Box>
              </Stack>
            )}
            {tagId && (
              <Alert severity="success" sx={{ mt: 1 }}>
                {t('content.card_detected', { id: tagId })}
                <br />
                {t('content.card_next')}
              </Alert>
            )}
          </Box>
        )}
      </Box>

      <Divider />

      <Box>
        <Typography variant="subtitle2" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <LibraryMusicIcon fontSize="small" /> {t('content.media')}
        </Typography>
        <Typography variant="caption" color="text.secondary">
          {t('content.media_hint')}
        </Typography>
        <Box sx={{ mt: 1 }}>
          <Button size="small" variant="outlined" onClick={() => navigate('/media')}>
            {t('content.media_open')}
          </Button>
        </Box>
      </Box>
    </Stack>
  );
};
