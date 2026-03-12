import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Box, Chip, CircularProgress, Drawer, IconButton, Typography } from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import NfcIcon from '@mui/icons-material/Nfc';
import EditIcon from '@mui/icons-material/Edit';
import MusicNoteIcon from '@mui/icons-material/MusicNote';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useWebSocket } from '@/contexts/WebSocketContext';
import type { RFIDScannedMessage, Tag } from '@/types/api';
import { tagsApi } from '@/api/tags';
import { ActionButton } from '@/components/ui/ActionButton';

const AUTO_CLOSE_SEC = 5;

/** Normalize tag id for comparison (UID string, case-insensitive, trim). */
function normalizeTagId(id: string | number): string {
  return String(id).trim().toLowerCase();
}

interface RfidScanDrawerProps {
  onAssignNew: (tagId: string) => void;
}

export const RfidScanDrawer: React.FC<RfidScanDrawerProps> = ({ onAssignNew }) => {
  const { t } = useTranslation('rfid');
  const navigate = useNavigate();
  const { lastMessage } = useWebSocket();

  const [open, setOpen] = useState(false);
  const [scannedTagId, setScannedTagId] = useState<string | null>(null);
  const [existingTag, setExistingTag] = useState<Tag | null>(null);
  const [loading, setLoading] = useState(false);
  const [countdown, setCountdown] = useState(AUTO_CLOSE_SEC);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const handleClose = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    setOpen(false);
    setScannedTagId(null);
    setExistingTag(null);
    setCountdown(AUTO_CLOSE_SEC);
  }, []);

  // Reagieren auf rfid_scanned: Drawer öffnen, Tag laden (ohne Countdown hier zu starten)
  useEffect(() => {
    if (lastMessage?.type !== 'rfid_scanned') return;
    const msg = lastMessage as RFIDScannedMessage;
    const rawTagId = msg.data.tag_id;
    const tagIdStr = String(rawTagId).trim();
    setScannedTagId(tagIdStr);
    setExistingTag(null);
    setCountdown(AUTO_CLOSE_SEC);
    setOpen(true);

    setLoading(true);
    tagsApi.getAll()
      .then((tags) => {
        const normalized = normalizeTagId(rawTagId);
        const found = tags.find((tag) => normalizeTagId(tag.tag_id) === normalized) ?? null;
        setExistingTag(found);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [lastMessage]);

  // Countdown nur von open abhängig – bleibt laufen, auch wenn lastMessage sich ändert (z. B. audio_status)
  useEffect(() => {
    if (!open) return;
    setCountdown(AUTO_CLOSE_SEC);
    timerRef.current = setInterval(() => {
      setCountdown((prev) => {
        if (prev <= 1) {
          if (timerRef.current) {
            clearInterval(timerRef.current);
            timerRef.current = null;
          }
          handleClose();
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [open, handleClose]);

  const handleAssign = () => {
    if (!scannedTagId) return;
    handleClose();
    navigate('/rfid');
    onAssignNew(scannedTagId);
  };

  return (
    <Drawer
      anchor="bottom"
      open={open}
      onClose={handleClose}
      PaperProps={{
        sx: {
          borderTopLeftRadius: 16,
          borderTopRightRadius: 16,
          px: 3,
          py: 2,
          maxWidth: 480,
          mx: 'auto',
          left: 0,
          right: 0,
        },
      }}
    >
      {/* Handle bar */}
      <Box
        sx={{
          width: 40,
          height: 4,
          bgcolor: 'divider',
          borderRadius: 2,
          mx: 'auto',
          mb: 2,
        }}
      />

      {/* Header with countdown */}
      <Box display="flex" alignItems="center" justifyContent="space-between" mb={2}>
        <Box display="flex" alignItems="center" gap={1}>
          <NfcIcon color="primary" />
          <Typography variant="h6" fontWeight={700}>
            {t('drawer.title')}
          </Typography>
        </Box>
        <Box display="flex" alignItems="center" gap={1}>
          <Box sx={{ position: 'relative', display: 'inline-flex' }}>
            <CircularProgress
              variant="determinate"
              value={(countdown / AUTO_CLOSE_SEC) * 100}
              size={40}
              thickness={3}
              sx={{ color: 'primary.main' }}
            />
            <Box
              sx={{
                top: 0,
                left: 0,
                bottom: 0,
                right: 0,
                position: 'absolute',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <Typography variant="caption" component="span" fontWeight={700} color="primary.main">
                {countdown}
              </Typography>
            </Box>
          </Box>
          <Typography variant="caption" color="text.secondary">
            {t('drawer.closes_in')}
          </Typography>
          <IconButton size="small" onClick={handleClose}>
            <CloseIcon fontSize="small" />
          </IconButton>
        </Box>
      </Box>

      {/* Tag ID */}
      <Typography variant="caption" color="text.secondary" display="block" mb={2}>
        {t('fields.tag_id')}: <strong>{scannedTagId}</strong>
      </Typography>

      {loading ? (
        <Typography variant="body2" color="text.secondary">
          {t('drawer.loading')}
        </Typography>
      ) : existingTag ? (
        /* ── Known tag ──────────────────────────────────────────────── */
        <Box
          sx={{
            p: 2,
            borderRadius: 2,
            border: '1px solid',
            borderColor: 'primary.light',
            bgcolor: 'action.hover',
            mb: 2,
          }}
        >
          <Box display="flex" alignItems="center" gap={1} mb={1}>
            <MusicNoteIcon fontSize="small" color="primary" />
            <Typography variant="subtitle2" fontWeight={700}>
              {existingTag.name ?? existingTag.tag_id}
            </Typography>
          </Box>
          <Chip
            label={`${existingTag.content_type === 'playlist' ? '▶ Playlist' : '♪ Track'} #${existingTag.content_id}`}
            size="small"
            color="primary"
            variant="outlined"
          />
        </Box>
      ) : (
        /* ── Unknown tag ────────────────────────────────────────────── */
        <Box
          sx={{
            p: 2,
            borderRadius: 2,
            border: '1px dashed',
            borderColor: 'warning.main',
            bgcolor: 'warning.lighter',
            mb: 2,
          }}
        >
          <Typography variant="body2" color="warning.dark" fontWeight={600}>
            {t('notification.unknown_tag')}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {t('drawer.assign_hint')}
          </Typography>
        </Box>
      )}

      {/* Actions */}
      <Box display="flex" gap={1} justifyContent="flex-end">
        <ActionButton actionType="secondary" onClick={handleClose}>
          {t('cancel', { ns: 'common' })}
        </ActionButton>
        {existingTag ? (
          <ActionButton
            actionType="secondary"
            startIcon={<EditIcon />}
            onClick={() => {
              handleClose();
              navigate('/rfid');
            }}
          >
            {t('edit_tag')}
          </ActionButton>
        ) : (
          <ActionButton
            actionType="primary"
            startIcon={<EditIcon />}
            onClick={handleAssign}
          >
            {t('notification.assign_now')}
          </ActionButton>
        )}
      </Box>
    </Drawer>
  );
};
