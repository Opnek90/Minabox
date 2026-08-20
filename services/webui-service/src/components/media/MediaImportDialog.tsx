import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Alert,
  Avatar,
  Box,
  Checkbox,
  CircularProgress,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  FormControlLabel,
  LinearProgress,
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
import { ResponsiveDialog } from '@/components/common/ResponsiveDialog';

const CONFIRM_CHECKBOX_ID = 'media-import-confirm';
const CONFIRM_HINT_ID = 'media-import-confirm-hint';

const POLL_INTERVAL_MS = 2000;
const POLL_TIMEOUT_MS = 300_000; // 5 minutes

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
  const [importing, setImporting] = useState(false);
  const [downloadStatus, setDownloadStatus] = useState<string | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  // Mandatory lawful-use confirmation. Gates both "check" and "import"; kept in
  // component state only – it is never persisted or reported anywhere, so it is
  // a deliberate user action, not a stored legal record.
  const [confirmed, setConfirmed] = useState(false);

  // Editable metadata, pre-filled from the preview once the URL is checked —
  // lets the user fix a wrong/missing title before the track is actually created.
  const [editTitle, setEditTitle] = useState('');
  const [editArtist, setEditArtist] = useState('');
  const [editAlbum, setEditAlbum] = useState('');

  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pollStartRef = useRef<number>(0);

  const stopPolling = useCallback(() => {
    if (pollTimerRef.current !== null) {
      clearTimeout(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }, []);

  // Cleanup on unmount
  useEffect(() => () => stopPolling(), [stopPolling]);

  // Re-opening the dialog always starts from an unconfirmed state – the parent
  // keeps this component mounted, so without this the previous confirmation
  // would still be ticked.
  useEffect(() => {
    if (open) {
      setConfirmed(false);
    }
  }, [open]);

  const handleReset = useCallback(() => {
    stopPolling();
    setUrl('');
    setPreview(null);
    setPreviewError(null);
    setConfirmed(false);
    setValidating(false);
    setImporting(false);
    setDownloadStatus(null);
    setEditTitle('');
    setEditArtist('');
    setEditAlbum('');
  }, [stopPolling]);

  const handleClose = () => {
    if (!importing) {
      handleReset();
      onClose();
    }
  };

  const startPolling = useCallback(
    (trackId: number) => {
      pollStartRef.current = Date.now();

      const poll = async () => {
        if (Date.now() - pollStartRef.current > POLL_TIMEOUT_MS) {
          setImporting(false);
          setDownloadStatus('error');
          showError(t('media_import.error'));
          return;
        }

        try {
          const statusData = await tracksApi.getDownloadStatus(trackId);
          setDownloadStatus(statusData.status);

          if (statusData.status === 'done') {
            // Fetch the fully-populated track and notify parent
            const track = await tracksApi.getById(trackId);
            showSuccess(t('media_import.success', { title: track.title }));
            onSuccess(track);
            handleReset();
            return;
          }

          if (statusData.status === 'error') {
            setImporting(false);
            showError(t('media_import.error'));
            return;
          }

          // pending | downloading → keep polling
          pollTimerRef.current = setTimeout(poll, POLL_INTERVAL_MS);
        } catch {
          // Network glitch – retry after a longer interval
          pollTimerRef.current = setTimeout(poll, POLL_INTERVAL_MS * 2);
        }
      };

      pollTimerRef.current = setTimeout(poll, POLL_INTERVAL_MS);
    },
    [handleReset, onSuccess, showError, showSuccess, t],
  );

  const handleValidate = async () => {
    if (!url.trim() || !confirmed) return;
    setValidating(true);
    setPreview(null);
    setPreviewError(null);
    try {
      const info = await tracksApi.validateUrl(url.trim()) as MediaPreview;
      setPreview(info);
      setEditTitle(info.title ?? '');
      setEditArtist(info.artist ?? '');
      setEditAlbum('');
    } catch {
      setPreviewError(t('media_import.preview_error'));
    } finally {
      setValidating(false);
    }
  };

  const handleImport = async () => {
    if (!url.trim() || !confirmed) return;
    setImporting(true);
    setDownloadStatus('pending');
    try {
      const { track_id, status } = await tracksApi.fromUrl(url.trim(), {
        title: editTitle.trim() || undefined,
        artist: editArtist.trim() || undefined,
        album: editAlbum.trim() || undefined,
      });

      if (status === 'done') {
        // Duplicate – already fully downloaded
        const track = await tracksApi.getById(track_id);
        showSuccess(t('media_import.success', { title: track.title }));
        onSuccess(track);
        handleReset();
        return;
      }

      // status === 'pending' → start polling
      startPolling(track_id);
    } catch {
      showError(t('media_import.error'));
      setImporting(false);
      setDownloadStatus(null);
    }
  };

  const isDownloading = importing && (downloadStatus === 'pending' || downloadStatus === 'downloading');

  return (
    <ResponsiveDialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ fontSize: '1.25rem', fontWeight: 600 }}>
        {t('media_import.title')}
      </DialogTitle>

      <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: 2 }}>
        {/* Lawful-use notice with its mandatory confirmation */}
        <Alert severity="warning" icon={<WarningAmberIcon />} sx={{ borderRadius: 2 }}>
          <Typography variant="body2" fontWeight={600}>
            {t('media_import.disclaimer_title')}
          </Typography>
          <Typography variant="caption" display="block" mt={0.5}>
            {t('media_import.disclaimer_body')}
          </Typography>
          <FormControlLabel
            sx={{ mt: 1, ml: 0, alignItems: 'flex-start' }}
            control={
              <Checkbox
                id={CONFIRM_CHECKBOX_ID}
                size="small"
                checked={confirmed}
                onChange={(e) => setConfirmed(e.target.checked)}
                disabled={isDownloading}
                inputProps={{
                  'aria-describedby': confirmed ? undefined : CONFIRM_HINT_ID,
                }}
                sx={{ pt: 0, pl: 0, mr: 1 }}
              />
            }
            label={
              <Typography variant="caption" component="span">
                {t('media_import.confirm_label')}
              </Typography>
            }
          />
          {!confirmed && (
            <Typography
              id={CONFIRM_HINT_ID}
              variant="caption"
              display="block"
              sx={{ mt: 0.25, fontStyle: 'italic' }}
            >
              {t('media_import.confirm_hint')}
            </Typography>
          )}
        </Alert>

        {/* URL Input */}
        <Box display="flex" gap={1} alignItems="flex-start">
          <TextField
            label={t('media_import.url_label')}
            placeholder={t('media_import.url_placeholder')}
            value={url}
            onChange={(e) => {
              setUrl(e.target.value);
              if (preview || previewError) {
                setPreview(null);
                setPreviewError(null);
              }
            }}
            onKeyDown={(e) => e.key === 'Enter' && !validating && handleValidate()}
            fullWidth
            size="small"
            disabled={isDownloading}
          />
          <ActionButton
            actionType="secondary"
            onClick={handleValidate}
            disabled={!url.trim() || !confirmed || validating || isDownloading}
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

        {/* Preview + editable metadata — user can fix a wrong/missing title
            etc. before the track is actually created (see handleImport) */}
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
                <Typography variant="caption" color="text.secondary" display="block">
                  {t('media_import.edit_hint', { defaultValue: 'Angaben vor dem Import anpassen:' })}
                </Typography>
                {preview.duration_ms != null && (
                  <Typography variant="caption" color="text.secondary">
                    {formatTime(preview.duration_ms)}
                  </Typography>
                )}
              </Box>
            </Stack>
            <TextField
              label={t('tracks.fields.title')}
              value={editTitle}
              onChange={(e) => setEditTitle(e.target.value)}
              fullWidth
              size="small"
              required
              disabled={isDownloading}
            />
            <TextField
              label={t('tracks.fields.artist')}
              value={editArtist}
              onChange={(e) => setEditArtist(e.target.value)}
              fullWidth
              size="small"
              disabled={isDownloading}
            />
            <TextField
              label={t('tracks.fields.album')}
              value={editAlbum}
              onChange={(e) => setEditAlbum(e.target.value)}
              fullWidth
              size="small"
              placeholder="Downloads"
              disabled={isDownloading}
            />
          </>
        )}

        {/* Download progress */}
        {isDownloading && (
          <Box>
            <Box display="flex" alignItems="center" gap={1.5} mb={0.75}>
              <CircularProgress size={16} />
              <Typography variant="caption" color="text.secondary">
                {downloadStatus === 'pending'
                  ? t('media_import.download_queued')
                  : t('media_import.downloading')}
              </Typography>
            </Box>
            <LinearProgress variant="indeterminate" sx={{ borderRadius: 1 }} />
          </Box>
        )}

        {/* Download error state */}
        {downloadStatus === 'error' && !importing && (
          <Alert severity="error" sx={{ borderRadius: 2 }}>
            {t('media_import.error')}
          </Alert>
        )}
      </DialogContent>

      <DialogActions>
        <ActionButton actionType="secondary" onClick={handleClose} disabled={isDownloading}>
          {t('cancel', { ns: 'common' })}
        </ActionButton>
        <ActionButton
          actionType="primary"
          onClick={handleImport}
          disabled={
            !url.trim() || !confirmed || isDownloading || (preview !== null && !editTitle.trim())
          }
          startIcon={isDownloading ? <CircularProgress size={16} /> : <DownloadIcon />}
        >
          {isDownloading ? t('media_import.downloading_short') : t('media_import.import')}
        </ActionButton>
      </DialogActions>
    </ResponsiveDialog>
  );
};
