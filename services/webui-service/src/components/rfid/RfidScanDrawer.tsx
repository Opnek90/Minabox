import React, { useEffect, useState } from 'react';
import {
  Box,
  Button,
  Chip,
  Drawer,
  IconButton,
  Typography,
} from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import NfcIcon from '@mui/icons-material/Nfc';
import EditIcon from '@mui/icons-material/Edit';
import MusicNoteIcon from '@mui/icons-material/MusicNote';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useWebSocket } from '@/contexts/WebSocketContext';
import type { RFIDScannedMessage, Tag } from '@/types/api';
import { tagsApi } from '@/api/tags';

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

  useEffect(() => {
    if (lastMessage?.type !== 'rfid_scanned') return;
    const msg = lastMessage as RFIDScannedMessage;
    const tagId = msg.data.tag_id;
    setScannedTagId(tagId);
    setExistingTag(null);
    setOpen(true);

    // Try to look up existing tag
    setLoading(true);
    tagsApi.getAll()
      .then((tags) => {
        const found = tags.find((t) => t.tag_id === tagId) ?? null;
        setExistingTag(found);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [lastMessage]);

  const handleClose = () => {
    setOpen(false);
    setScannedTagId(null);
    setExistingTag(null);
  };

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

      {/* Header */}
      <Box display="flex" alignItems="center" justifyContent="space-between" mb={2}>
        <Box display="flex" alignItems="center" gap={1}>
          <NfcIcon color="primary" />
          <Typography variant="h6" fontWeight={700}>
            {t('drawer.title', { defaultValue: 'Karte erkannt' })}
          </Typography>
        </Box>
        <IconButton size="small" onClick={handleClose}>
          <CloseIcon fontSize="small" />
        </IconButton>
      </Box>

      {/* Tag ID */}
      <Typography variant="caption" color="text.secondary" display="block" mb={2}>
        {t('fields.tag_id')}: <strong>{scannedTagId}</strong>
      </Typography>

      {loading ? (
        <Typography variant="body2" color="text.secondary">
          {t('drawer.loading', { defaultValue: 'Suche Tag…' })}
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
            {t('drawer.assign_hint', { defaultValue: 'Dieser Karte ist noch kein Inhalt zugewiesen.' })}
          </Typography>
        </Box>
      )}

      {/* Actions */}
      <Box display="flex" gap={1} justifyContent="flex-end">
        <Button onClick={handleClose} size="small">
          {t('cancel', { ns: 'common' })}
        </Button>
        {existingTag ? (
          <Button
            variant="outlined"
            size="small"
            startIcon={<EditIcon />}
            onClick={() => {
              handleClose();
              navigate('/rfid');
            }}
          >
            {t('edit_tag')}
          </Button>
        ) : (
          <Button
            variant="contained"
            size="small"
            startIcon={<EditIcon />}
            onClick={handleAssign}
          >
            {t('notification.assign_now')}
          </Button>
        )}
      </Box>
    </Drawer>
  );
};
