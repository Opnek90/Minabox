import React, { useState } from 'react';
import {
  Button,
  DialogActions,
  DialogContent,
  DialogTitle,
  TextField,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import { useToast } from '@/contexts/ToastContext';
import type { Stream } from '@/types/api';
import { streamsApi } from '@/api/streams';
import { isValidUrl } from '@/utils/validators';
import { CoverUploadField } from './CoverUploadField';
import { ResponsiveDialog } from '@/components/common/ResponsiveDialog';

interface StreamEditDialogProps {
  open: boolean;
  stream: Stream | null;
  onClose: () => void;
  onSuccess: (stream: Stream) => void;
}

export const StreamEditDialog: React.FC<StreamEditDialogProps> = ({
  open,
  stream,
  onClose,
  onSuccess,
}) => {
  const { t } = useTranslation('media');
  const { showSuccess, showError } = useToast();

  const [title, setTitle] = useState(stream?.title ?? '');
  const [artist, setArtist] = useState(stream?.artist ?? '');
  const [sourceUri, setSourceUri] = useState(stream?.source_uri ?? '');
  const [coverUrl, setCoverUrl] = useState<string | null>(stream?.cover_art_url ?? null);
  const [pendingCoverFile, setPendingCoverFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);

  React.useEffect(() => {
    if (stream && open) {
      setTitle(stream.title);
      setArtist(stream.artist ?? '');
      setSourceUri(stream.source_uri);
      setCoverUrl(stream.cover_art_url ?? null);
      setPendingCoverFile(null);
    }
  }, [stream, open]);

  const urlError = sourceUri && !isValidUrl(sourceUri) ? t('invalid_url', { ns: 'errors' }) : '';
  const isValid = title.trim() && sourceUri && isValidUrl(sourceUri);

  const handleSave = async () => {
    if (!stream || !isValid) return;
    setLoading(true);
    try {
      let updated = await streamsApi.update(stream.id, {
        title: title.trim(),
        artist: artist.trim() || null,
        source_uri: sourceUri.trim(),
      });
      if (pendingCoverFile) {
        updated = await streamsApi.uploadCover(stream.id, pendingCoverFile);
      }
      onSuccess(updated);
      showSuccess(t('streams.updated'));
      onClose();
    } catch {
      showError(t('streams.update_error'));
    } finally {
      setLoading(false);
    }
  };

  const handleRemoveCover = async () => {
    if (!stream) return;
    setCoverUrl(null);
    setPendingCoverFile(null);
    try {
      const updated = await streamsApi.deleteCover(stream.id);
      setCoverUrl(updated.cover_art_url ?? null);
      onSuccess(updated);
      showSuccess(t('streams.cover_removed'));
    } catch {
      showError(t('streams.cover_error'));
    }
  };

  const handleCoverSelect = (file: File | null) => {
    if (file) {
      setPendingCoverFile(file);
      setCoverUrl(URL.createObjectURL(file));
    } else {
      setPendingCoverFile(null);
      setCoverUrl(stream?.cover_art_url ?? null);
    }
  };

  const handleRemoveCoverInField = () => {
    if (pendingCoverFile) {
      setPendingCoverFile(null);
      setCoverUrl(stream?.cover_art_url ?? null);
    } else {
      handleRemoveCover();
    }
  };

  const displayCoverUrl = pendingCoverFile ? coverUrl : (coverUrl ?? stream?.cover_art_url ?? null);

  return (
    <ResponsiveDialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ fontSize: '1.25rem', fontWeight: 600 }}>
        {t('streams.edit')}
      </DialogTitle>
      <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: '16px !important' }}>
        <CoverUploadField
          displayUrl={displayCoverUrl}
          coverFile={pendingCoverFile}
          onFileSelect={handleCoverSelect}
          onRemove={handleRemoveCoverInField}
        />

        <TextField
          label={t('streams.fields.title')}
          placeholder={t('stream.fields.title_placeholder')}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          fullWidth
          size="small"
          required
        />
        <TextField
          label={t('streams.fields.artist')}
          value={artist}
          onChange={(e) => setArtist(e.target.value)}
          fullWidth
          size="small"
        />
        <TextField
          label={t('stream.url')}
          value={sourceUri}
          onChange={(e) => setSourceUri(e.target.value)}
          fullWidth
          size="small"
          error={!!urlError}
          helperText={urlError}
          required
        />
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('cancel', { ns: 'common' })}</Button>
        <Button onClick={handleSave} variant="contained" disabled={!isValid || loading}>
          {t('save', { ns: 'common' })}
        </Button>
      </DialogActions>
    </ResponsiveDialog>
  );
};
