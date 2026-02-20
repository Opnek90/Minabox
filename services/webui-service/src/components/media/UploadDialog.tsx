import React, { useCallback, useRef, useState } from 'react';
import {
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  LinearProgress,
  TextField,
  Typography,
} from '@mui/material';
import UploadFileIcon from '@mui/icons-material/UploadFile';
import AudioFileIcon from '@mui/icons-material/AudioFile';
import { useTranslation } from 'react-i18next';
import { useToast } from '@/contexts/ToastContext';
import type { Track } from '@/types/api';
import { tracksApi } from '@/api/tracks';


interface UploadDialogProps {
  open: boolean;
  onClose: () => void;
  onSuccess: (track: Track) => void;
}


export const UploadDialog: React.FC<UploadDialogProps> = ({ open, onClose, onSuccess }) => {
  const { t } = useTranslation('media');
  const { showError } = useToast();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState('');
  const [artist, setArtist] = useState('');
  const [album, setAlbum] = useState('');
  const [progress, setProgress] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);

  const applyFile = useCallback((selected: File) => {
    setFile(selected);
    setTitle((prev) => prev || selected.name.replace(/\.[^.]+$/, ''));
  }, []);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0] ?? null;
    if (selected) applyFile(selected);
  };

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const dropped = e.dataTransfer.files[0];
    if (dropped) applyFile(dropped);
  }, [applyFile]);

  const handleReset = () => {
    setFile(null);
    setTitle('');
    setArtist('');
    setAlbum('');
    setProgress(0);
    setDragOver(false);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    setProgress(0);
    try {
      const track = await tracksApi.upload(
        file,
        { title: title || undefined, artist: artist || undefined, album: album || undefined },
        setProgress
      );
      onSuccess(track);
      handleReset();
    } catch {
      showError(t('upload.error', { defaultValue: 'Upload fehlgeschlagen' }));
    } finally {
      setUploading(false);
    }
  };

  const handleClose = () => {
    if (!uploading) {
      handleReset();
      onClose();
    }
  };

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ fontSize: '1.25rem', fontWeight: 600 }}>{t('upload.title')}</DialogTitle>
      <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: 2 }}>
        <input
          ref={fileInputRef}
          type="file"
          accept="audio/*,.mp3,.ogg,.flac,.wav,.m4a,.aac"
          onChange={handleFileSelect}
          style={{ display: 'none' }}
        />

        {/* Drop Zone */}
        <Box
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
          sx={{
            border: '2px dashed',
            borderColor: dragOver ? 'primary.main' : file ? 'success.main' : 'divider',
            bgcolor: dragOver ? 'primary.50' : file ? 'success.50' : 'background.paper',
            borderRadius: 2,
            p: 3,
            textAlign: 'center',
            cursor: 'pointer',
            transition: 'all 0.2s ease',
            '&:hover': { borderColor: 'primary.light', bgcolor: 'action.hover' },
          }}
        >
          {file ? (
            <>
              <AudioFileIcon sx={{ fontSize: 40, color: 'success.main', mb: 1 }} />
              <Typography variant="body2" fontWeight={600} color="success.main">
                {file.name}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {(file.size / (1024 * 1024)).toFixed(1)} MB – {t('upload.select_file')}
              </Typography>
            </>
          ) : (
            <>
              <UploadFileIcon
                sx={{ fontSize: 40, color: dragOver ? 'primary.main' : 'text.disabled', mb: 1 }}
              />
              <Typography variant="body2" color={dragOver ? 'primary.main' : 'text.secondary'}>
                {dragOver ? t('upload.drop_zone_active') : t('upload.drop_zone')}
              </Typography>
            </>
          )}
        </Box>

        <Typography variant="caption" color="text.secondary">
          {t('upload.supported_formats')}
        </Typography>

        <TextField
          label={t('upload.fields.title')}
          placeholder={t('upload.fields.title_placeholder')}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          fullWidth size="small"
        />
        <TextField
          label={t('upload.fields.artist')}
          placeholder={t('upload.fields.artist_placeholder')}
          value={artist}
          onChange={(e) => setArtist(e.target.value)}
          fullWidth size="small"
        />
        <TextField
          label={t('upload.fields.album')}
          placeholder={t('upload.fields.album_placeholder')}
          value={album}
          onChange={(e) => setAlbum(e.target.value)}
          fullWidth size="small"
        />

        {uploading && (
          <>
            <LinearProgress variant="determinate" value={progress} sx={{ borderRadius: 1 }} />
            <Typography variant="caption" textAlign="center">
              {t('upload.progress', { percent: progress })}
            </Typography>
          </>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={handleClose} disabled={uploading}>
          {t('cancel', { ns: 'common' })}
        </Button>
        <Button onClick={handleUpload} variant="contained" disabled={!file || uploading}>
          {uploading ? t('upload.uploading') : t('upload.title')}
        </Button>
      </DialogActions>
    </Dialog>
  );
};
