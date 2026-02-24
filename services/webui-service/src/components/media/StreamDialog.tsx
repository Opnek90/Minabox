import React, { useState } from 'react';
import {
  Button,
  Dialog,
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

interface StreamDialogProps {
  open: boolean;
  onClose: () => void;
  onSuccess: (stream: Stream) => void;
}

export const StreamDialog: React.FC<StreamDialogProps> = ({ open, onClose, onSuccess }) => {
  const { t } = useTranslation('media');
  const { showError } = useToast();

  const [url, setUrl] = useState('');
  const [title, setTitle] = useState('');
  const [artist, setArtist] = useState('');
  const [coverFile, setCoverFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);

  const urlError = url && !isValidUrl(url) ? t('invalid_url', { ns: 'errors' }) : '';
  const isValid = url && title && isValidUrl(url);

  const handleSave = async () => {
    if (!isValid) return;
    setLoading(true);
    try {
      let stream = await streamsApi.create({
        title,
        artist: artist || null,
        source_uri: url,
      });
      if (coverFile) {
        stream = await streamsApi.uploadCover(stream.id, coverFile);
      }
      onSuccess(stream);
      handleReset();
    } catch {
      showError(t('stream.error', { defaultValue: 'Stream konnte nicht gespeichert werden' }));
    } finally {
      setLoading(false);
    }
  };

  const handleReset = () => {
    setUrl('');
    setTitle('');
    setArtist('');
    setCoverFile(null);
  };

  const handleClose = () => {
    handleReset();
    onClose();
  };

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ fontSize: '1.25rem', fontWeight: 600 }}>{t('stream.title')}</DialogTitle>
      <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: '16px !important' }}>
        <CoverUploadField
          displayUrl={coverFile ? URL.createObjectURL(coverFile) : null}
          coverFile={coverFile}
          onFileSelect={(file) => setCoverFile(file)}
          onRemove={() => setCoverFile(null)}
        />
        <TextField
          label={t('stream.url')}
          placeholder={t('stream.url_placeholder')}
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          fullWidth size="small"
          error={!!urlError}
          helperText={urlError || (url ? undefined : t('stream.url_hint'))}
          required
        />
        <TextField
          label={t('stream.fields.title')}
          placeholder={t('stream.fields.title_placeholder')}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          fullWidth size="small"
          required
        />
        <TextField
          label={t('stream.fields.artist')}
          value={artist}
          onChange={(e) => setArtist(e.target.value)}
          fullWidth size="small"
        />
      </DialogContent>
      <DialogActions>
        <Button onClick={handleClose}>{t('cancel', { ns: 'common' })}</Button>
        <Button onClick={handleSave} variant="contained" disabled={!isValid || loading}>
          {t('add', { ns: 'common' })}
        </Button>
      </DialogActions>
    </Dialog>
  );
};
