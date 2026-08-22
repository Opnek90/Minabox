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
import type { Track } from '@/types/api';
import { tracksApi } from '@/api/tracks';
import { CoverUploadField } from './CoverUploadField';
import { ResponsiveDialog } from '@/components/common/ResponsiveDialog';

interface RemoteTrackDialogProps {
  open: boolean;
  onClose: () => void;
  onSuccess: (track: Track) => void;
}

export const RemoteTrackDialog: React.FC<RemoteTrackDialogProps> = ({
  open,
  onClose,
  onSuccess,
}) => {
  const { t } = useTranslation('media');
  const { showError } = useToast();
  const [title, setTitle] = useState('');
  const [artist, setArtist] = useState('');
  const [album, setAlbum] = useState('');
  const [sourceUri, setSourceUri] = useState('');
  const [coverFile, setCoverFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);

  const isValid = title.trim() && sourceUri.trim();

  const handleSave = async () => {
    if (!isValid) return;
    setLoading(true);
    try {
      let track = await tracksApi.create({
        title: title.trim(),
        artist: artist.trim() || null,
        album: album.trim() || null,
        source_type: 'remote',
        source_uri: sourceUri.trim(),
      });
      if (coverFile) {
        track = await tracksApi.uploadCover(track.id, coverFile);
      }
      onSuccess(track);
      handleReset();
      onClose();
    } catch {
      showError(
        t('tracks.remote_error')
      );
    } finally {
      setLoading(false);
    }
  };

  const handleReset = () => {
    setTitle('');
    setArtist('');
    setAlbum('');
    setSourceUri('');
    setCoverFile(null);
  };

  const handleClose = () => {
    handleReset();
    onClose();
  };

  return (
    <ResponsiveDialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ fontSize: '1.25rem', fontWeight: 600 }}>
        {t('tracks.add_remote')}
      </DialogTitle>
      <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: '16px !important' }}>
        <CoverUploadField
          displayUrl={coverFile ? URL.createObjectURL(coverFile) : null}
          coverFile={coverFile}
          onFileSelect={(file) => setCoverFile(file)}
          onRemove={() => setCoverFile(null)}
        />
        <TextField
          label={t('tracks.fields.title')}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          fullWidth
          size="small"
          required
        />
        <TextField
          label={t('tracks.fields.artist')}
          value={artist}
          onChange={(e) => setArtist(e.target.value)}
          fullWidth
          size="small"
        />
        <TextField
          label={t('tracks.fields.album')}
          value={album}
          onChange={(e) => setAlbum(e.target.value)}
          fullWidth
          size="small"
        />
        <TextField
          label={t('tracks.fields.source_uri')}
          value={sourceUri}
          onChange={(e) => setSourceUri(e.target.value)}
          fullWidth
          size="small"
          required
          placeholder="smb://server/share/path.mp3"
          helperText={t('tracks.fields.source_uri_hint')}
        />
      </DialogContent>
      <DialogActions>
        <Button onClick={handleClose}>{t('cancel', { ns: 'common' })}</Button>
        <Button
          variant="contained"
          onClick={handleSave}
          disabled={!isValid || loading}
        >
          {t('add', { ns: 'common' })}
        </Button>
      </DialogActions>
    </ResponsiveDialog>
  );
};
