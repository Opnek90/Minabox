import React, { useState } from 'react';
import {
  Alert,
  Avatar,
  Box,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import DownloadIcon from '@mui/icons-material/Download';
import MusicNoteIcon from '@mui/icons-material/MusicNote';
import WarningAmberIcon from '@mui/icons-material/WarningAmber';
import { useTranslation } from 'react-i18next';
import { tracksApi } from '@/api/tracks';
import { useToast } from '@/contexts/ToastContext';
import type { Track } from '@/types/api';
import { ActionButton } from '@/components/ui/ActionButton';
import { formatTime } from '@/utils/formatTime';

interface MediaPreview {
  valid: boolean;
  title: string;
  artist: string | null;
  duration_ms: number | null;
  thumbnail_url: string | null;
  video_id: string;
}

interface MediaImportDialogProps {
  open: boolean;
  onClose: () => void;
  onSuccess: (track: Track) => void;
}

export const MediaImportDialog: React.FC<MediaImportDialogProps> = ({
  open,
  onClose,
  onSuccess,
}) => {
  const { t } = useTranslation('media');
  const { showError, showSuccess } = useToast();

  const [url, setUrl] = useState('');
  const [preview, setPreview] = useState<MediaPreview | null>(null);
  const [validating, setValidating] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

  const handleReset = () => {
    setUrl('');
    setPreview(null);
    setPreviewError(null);
    setValidating(false);
    setDownloading(false);
  };

  const handleClose = () => {
    if (!downloading) {
      handleReset();
      onClose();
    }
  };

  const handleValidate = async () => {
    if (!url.trim()) return;
    setValidating(true);
    setPreview(null);
    setPreviewError(null);
    try {
      const info = await tracksApi.validateUrl(url.trim());
      setPreview(info as MediaPreview);
    } catch {
      setPreviewError(t('media_import.preview_error'));
    } finally {
      setValidating(false);
    }
  };

  const handleImport = async () => {
    if (!url.trim()) return;
    setDownloading(true);
    try {
      const track = await tracksApi.fromUrl(url.trim());
      showSuccess(t('media_import.success', { title: track.title }));
      onSuccess(track);
      handleReset();
    } catch {
      showError(t('media_import.error'));
    } finally {
      setDownloading(false);
    }
  };

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ fontSize: '1.25rem', fontWeight: 600 }}>
        {t('media_import.title')}
      </DialogTitle>

      <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: 2 }}>
        {/* Disclaimer */}
        <Alert severity="warning" icon={<WarningAmberIcon />} sx={{ borderRadius: 2 }}>
          <Typography variant="body2" fontWeight={600}>
            {t('media_import.disclaimer_title')}
          </Typography>
          <Typography variant="caption" display="block" mt={0.5}>
            {t('media_import.disclaimer_body')}
          </Typography>
        </Alert>

        {/* URL Input */}
        <Box display="flex" gap={1} alignItems="flex-start">
          <TextField
            label={t('media_import.url_label')}
            placeholder={t('media_import.url_placeholder')}
            value={url}
            onChange={(e) => {
              setUrl(e.target.value);
              // Reset preview when URL changes
              if (preview || previewError) {
                setPreview(null);
                setPreviewError(null);
              }
            }}
            onKeyDown={(e) => e.key === 'Enter' && !validating && handleValidate()}
            fullWidth
            size="small"
            disabled={downloading}
          />
          <ActionButton
            actionType="secondary"
            onClick={handleValidate}
            disabled={!url.trim() || validating || downloading}
            sx={{ whiteSpace: 'nowrap', flexShrink: 0, mt: 0.25 }}
          >
            {validating ? (
              <CircularProgress size={16} />
            ) : (
              t('media_import.check')
            )}
          </ActionButton>
        </Box>

        {/* Preview error */}
        {previewError && (
          <Alert severity="error" sx={{ borderRadius: 2 }}>
            {previewError}
          </Alert>
        )}

        {/* Preview card */}
        {preview && (
          <>
            <Divider />
            <Stack direction="row" spacing={2} alignItems="center">
              {preview.thumbnail_url ? (
                <Avatar
                  src={preview.thumbnail_url}
                  variant="rounded"
                  sx={{ width: 72, height: 72 }}
                />
              ) : (
                <Avatar variant="rounded" sx={{ width: 72, height: 72, bgcolor: 'action.selected' }}>
                  <MusicNoteIcon />
                </Avatar>
              )}
              <Box flex={1} minWidth={0}>
                <Typography variant="subtitle1" fontWeight={600} noWrap>
                  {preview.title}
                </Typography>
                {preview.artist && (
                  <Typography variant="body2" color="text.secondary" noWrap>
                    {preview.artist}
                  </Typography>
                )}
                {preview.duration_ms != null && (
                  <Typography variant="caption" color="text.disabled">
                    {formatTime(preview.duration_ms)}
                  </Typography>
                )}
              </Box>
            </Stack>
          </>
        )}

        {/* Download progress hint */}
        {downloading && (
          <Box display="flex" alignItems="center" gap={1.5}>
            <CircularProgress size={18} />
            <Typography variant="caption" color="text.secondary">
              {t('media_import.downloading')}
            </Typography>
          </Box>
        )}
      </DialogContent>

      <DialogActions>
        <ActionButton actionType="secondary" onClick={handleClose} disabled={downloading}>
          {t('cancel', { ns: 'common' })}
        </ActionButton>
        <ActionButton
          actionType="primary"
          onClick={handleImport}
          disabled={!url.trim() || downloading}
          startIcon={downloading ? <CircularProgress size={16} /> : <DownloadIcon />}
        >
          {downloading ? t('media_import.downloading_short') : t('media_import.import')}
        </ActionButton>
      </DialogActions>
    </Dialog>
  );
};
