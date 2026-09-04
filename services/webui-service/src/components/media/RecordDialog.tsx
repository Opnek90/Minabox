import React, { useCallback, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Box,
  DialogActions,
  DialogContent,
  DialogTitle,
  LinearProgress,
  TextField,
  Typography,
} from '@mui/material';
import AudioFileIcon from '@mui/icons-material/AudioFile';
import MicIcon from '@mui/icons-material/Mic';
import ReplayIcon from '@mui/icons-material/Replay';
import StopIcon from '@mui/icons-material/Stop';
import { useTranslation } from 'react-i18next';
import { useToast } from '@/contexts/ToastContext';
import type { Track } from '@/types/api';
import { tracksApi } from '@/api/tracks';
import { ActionButton } from '@/components/ui/ActionButton';
import { ResponsiveDialog } from '@/components/common/ResponsiveDialog';
import { useObjectUrl } from '@/hooks/useObjectUrl';
import { recordingSupported, useAudioRecorder } from '@/hooks/useAudioRecorder';

/**
 * Record a personal message and put it in the library as an ordinary track.
 *
 * The message is not a special kind of content: it is uploaded through the
 * same route as any other file and ends up as a `file` track, so playlists,
 * resume positions and the statistics need to know nothing about it. Assigning
 * it to a card happens afterwards, where every other track is assigned.
 *
 * Where there is no microphone to be had - which is every plain-HTTP origin
 * except localhost, and that is how the box is normally reached - the dialog
 * says so and offers the way that does work: record with the phone's own voice
 * memo app and pick the file here. That is a smaller feature, not a broken
 * one, and it is better than a button that silently does nothing.
 */

/** The user's answer to "how long may a message be" - 15 minutes. */
const MAX_DURATION_MS = 15 * 60 * 1000;

/** Below this a "recording" is a slip of the finger, not a message. */
const MIN_DURATION_MS = 500;

interface RecordDialogProps {
  open: boolean;
  onClose: () => void;
  onSuccess: (track: Track) => void;
  /** When set, the recording is placed directly into this folder. */
  currentFolderId?: number | null;
}

/** mm:ss - a message is never long enough to need hours. */
const formatDuration = (ms: number): string => {
  const total = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${minutes}:${String(seconds).padStart(2, '0')}`;
};

export const RecordDialog: React.FC<RecordDialogProps> = ({
  open,
  onClose,
  onSuccess,
  currentFolderId,
}) => {
  const { t } = useTranslation(['media', 'errors']);
  const { showError } = useToast();
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Evaluated once per mount: whether the API exists cannot change while the
  // dialog is open, and calling it during render keeps the branch obvious.
  const supported = useMemo(() => recordingSupported(), []);
  const { status, error, elapsedMs, recording, start, stop, reset } = useAudioRecorder({
    maxDurationMs: MAX_DURATION_MS,
  });

  const [pickedFile, setPickedFile] = useState<File | null>(null);
  const [title, setTitle] = useState('');
  const [artist, setArtist] = useState('');
  const [progress, setProgress] = useState(0);
  const [saving, setSaving] = useState(false);

  const audioFile = recording?.file ?? pickedFile;
  const previewUrl = useObjectUrl(audioFile);

  const clearAll = useCallback(() => {
    reset();
    setPickedFile(null);
    setTitle('');
    setArtist('');
    setProgress(0);
    if (fileInputRef.current) fileInputRef.current.value = '';
  }, [reset]);

  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const selected = event.target.files?.[0] ?? null;
    if (!selected) return;
    setPickedFile(selected);
    setTitle((prev) => prev || selected.name.replace(/\.[^.]+$/, ''));
  };

  const handleSave = async () => {
    if (!audioFile || !title.trim()) return;
    setSaving(true);
    setProgress(0);
    try {
      const track = await tracksApi.upload(
        audioFile,
        {
          title: title.trim(),
          artist: artist.trim() || undefined,
          folderId: currentFolderId ?? null,
          // Only the recorder knows this; a picked file brings its own.
          durationMs: recording?.durationMs,
        },
        setProgress,
      );
      onSuccess(track);
      clearAll();
    } catch {
      showError(t('errors:upload_failed'));
    } finally {
      setSaving(false);
    }
  };

  const handleClose = () => {
    if (saving) return;
    clearAll();
    onClose();
  };

  // "starting" is the wait for the browser's permission prompt: there is
  // nothing to stop yet, so the start button stays put and spins instead.
  const isRecording = status === 'recording';
  const isStarting = status === 'starting';
  const tooShort = recording !== null && recording.durationMs < MIN_DURATION_MS;
  const canSave =
    !!audioFile && !!title.trim() && !saving && !isRecording && !isStarting && !tooShort;

  const errorMessage = error
    ? {
        unsupported: t('record.error_unsupported'),
        denied: t('record.error_denied'),
        no_microphone: t('record.error_no_microphone'),
        failed: t('record.error_failed'),
      }[error]
    : null;

  return (
    <ResponsiveDialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ fontSize: '1.25rem', fontWeight: 600 }}>{t('record.title')}</DialogTitle>
      <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: 2 }}>
        <Typography variant="body2" color="text.secondary">
          {t('record.intro')}
        </Typography>

        {!supported && (
          <Alert severity="info">
            <Typography variant="body2" fontWeight={600}>
              {t('record.insecure_title')}
            </Typography>
            <Typography variant="body2">{t('record.insecure_body')}</Typography>
          </Alert>
        )}

        {errorMessage && <Alert severity="warning">{errorMessage}</Alert>}

        {supported && (
          <Box
            sx={{
              border: '2px dashed',
              borderColor: isRecording ? 'error.main' : recording ? 'success.main' : 'divider',
              borderRadius: 2,
              p: 3,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: 1.5,
            }}
          >
            <MicIcon
              sx={{
                fontSize: 40,
                color: isRecording ? 'error.main' : recording ? 'success.main' : 'text.disabled',
              }}
            />
            <Typography variant="h6" sx={{ fontVariantNumeric: 'tabular-nums' }}>
              {formatDuration(elapsedMs)} / {formatDuration(MAX_DURATION_MS)}
            </Typography>
            {isRecording && (
              <LinearProgress
                variant="determinate"
                color="error"
                value={Math.min(100, (elapsedMs / MAX_DURATION_MS) * 100)}
                sx={{ width: '100%', borderRadius: 1 }}
              />
            )}
            {isRecording ? (
              <ActionButton actionType="destructive" startIcon={<StopIcon />} onClick={stop}>
                {t('record.stop')}
              </ActionButton>
            ) : recording ? (
              <ActionButton actionType="secondary" startIcon={<ReplayIcon />} onClick={reset}>
                {t('record.again')}
              </ActionButton>
            ) : (
              <ActionButton
                actionType="primary"
                startIcon={<MicIcon />}
                loading={isStarting}
                disabled={isStarting}
                onClick={start}
              >
                {t('record.start')}
              </ActionButton>
            )}
            {tooShort && (
              <Typography variant="caption" color="error.main">
                {t('record.too_short')}
              </Typography>
            )}
          </Box>
        )}

        <input
          ref={fileInputRef}
          type="file"
          accept="audio/*"
          onChange={handleFileSelect}
          style={{ display: 'none' }}
        />
        {!recording && (
          <Box
            onClick={() => fileInputRef.current?.click()}
            sx={{
              border: '2px dashed',
              borderColor: pickedFile ? 'success.main' : 'divider',
              borderRadius: 2,
              p: 2,
              textAlign: 'center',
              cursor: 'pointer',
              '&:hover': { borderColor: 'primary.light', bgcolor: 'action.hover' },
            }}
          >
            <AudioFileIcon
              sx={{ fontSize: 32, color: pickedFile ? 'success.main' : 'text.disabled' }}
            />
            <Typography variant="body2" color={pickedFile ? 'success.main' : 'text.secondary'}>
              {pickedFile ? pickedFile.name : t('record.pick_file')}
            </Typography>
          </Box>
        )}

        {previewUrl && <audio controls src={previewUrl} style={{ width: '100%' }} />}

        <TextField
          label={t('record.fields.title')}
          placeholder={t('record.fields.title_placeholder')}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          fullWidth
          size="small"
          required
        />
        <TextField
          label={t('record.fields.artist')}
          placeholder={t('record.fields.artist_placeholder')}
          value={artist}
          onChange={(e) => setArtist(e.target.value)}
          fullWidth
          size="small"
        />

        {currentFolderId != null && (
          <Typography variant="caption" color="primary.main">
            {t('folders.upload_hint')}
          </Typography>
        )}

        {saving && (
          <>
            <LinearProgress variant="determinate" value={progress} sx={{ borderRadius: 1 }} />
            <Typography variant="caption" textAlign="center">
              {t('upload.progress', { percent: progress })}
            </Typography>
          </>
        )}
      </DialogContent>
      <DialogActions>
        <ActionButton actionType="secondary" onClick={handleClose} disabled={saving}>
          {t('cancel', { ns: 'common' })}
        </ActionButton>
        <ActionButton actionType="primary" loading={saving} onClick={handleSave} disabled={!canSave}>
          {saving ? t('record.saving') : t('record.save')}
        </ActionButton>
      </DialogActions>
    </ResponsiveDialog>
  );
};
