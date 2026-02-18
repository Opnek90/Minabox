import React, { useState } from 'react';
import {
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  TextField,
  Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import type { Track } from '@/types/api';
import { tracksApi } from '@/api/tracks';
import { isValidUrl } from '@/utils/validators';

interface StreamDialogProps {
  open: boolean;
  onClose: () => void;
  onSuccess: (track: Track) => void;
}

export const StreamDialog: React.FC<StreamDialogProps> = ({ open, onClose, onSuccess }) => {
  const { t } = useTranslation('media');

  const [url, setUrl] = useState('');
  const [title, setTitle] = useState('');
  const [artist, setArtist] = useState('');
  const [album, setAlbum] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const urlError = url && !isValidUrl(url) ? t('invalid_url', { ns: 'errors' }) : '';

  const handleSave = async () => {
    if (!url || !title || !isValidUrl(url)) return;
    setLoading(true);
    setError(null);
    try {
      const track = await tracksApi.create({
        title,
        artist: artist || null,
        album: album || null,
        source_type: 'stream',
        source_uri: url,
      });
      onSuccess(track);
      handleReset();
    } catch {
      setError('Stream konnte nicht gespeichert werden');
    } finally {
      setLoading(false);
    }
  };

  const handleReset = () => {
    setUrl('');
    setTitle('');
    setArtist('');
    setAlbum('');
    setError(null);
  };

  const handleClose = () => {
    handleReset();
    onClose();
  };

  const isValid = url && title && isValidUrl(url);

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ fontSize: '1.25rem', fontWeight: 600 }}>{t('stream.title')}</DialogTitle>
      <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: 2 }}>
        <TextField
          label={t('stream.url')}
          placeholder={t('stream.url_placeholder')}
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          fullWidth
          size="small"
          error={!!urlError}
          helperText={urlError || (url ? undefined : t('stream.url_hint'))}
          required
        />
        <TextField
          label={t('stream.fields.title')}
          placeholder={t('stream.fields.title_placeholder')}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          fullWidth
          size="small"
          required
        />
        <TextField
          label={t('stream.fields.artist')}
          value={artist}
          onChange={(e) => setArtist(e.target.value)}
          fullWidth
          size="small"
        />
        <TextField
          label={t('stream.fields.album')}
          value={album}
          onChange={(e) => setAlbum(e.target.value)}
          fullWidth
          size="small"
        />

        {error && (
          <Typography color="error" variant="body2">
            {error}
          </Typography>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={handleClose}>{t('cancel', { ns: 'common' })}</Button>
        <Button
          onClick={handleSave}
          variant="contained"
          disabled={!isValid || loading}
        >
          {t('add', { ns: 'common' })}
        </Button>
      </DialogActions>
    </Dialog>
  );
};
