import React, { useRef, useState } from 'react';
import {
  Box,
  Button,
  Card,
  CardActions,
  CardContent,
  CardMedia,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  Grid,
  IconButton,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import EditIcon from '@mui/icons-material/Edit';
import DeleteIcon from '@mui/icons-material/Delete';
import PlaylistPlayIcon from '@mui/icons-material/PlaylistPlay';
import QueueMusicIcon from '@mui/icons-material/QueueMusic';
import ImageIcon from '@mui/icons-material/Image';
import UploadIcon from '@mui/icons-material/Upload';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import { useTranslation } from 'react-i18next';
import { useToast } from '@/contexts/ToastContext';
import type { Playlist, PlaylistDetail, Track } from '@/types/api';
import { playlistsApi } from '@/api/playlists';
import { audioApi } from '@/api/audio';
import { PlaylistTracksDialog } from './PlaylistTracksDialog';


interface PlaylistListProps {
  playlists: Playlist[];
  tracks: Track[];
  onUpdate: (playlist: Playlist) => void;
  onDelete: (playlist: Playlist) => void;
  onCreate: (playlist: Playlist) => void;
}

interface PlaylistFormData {
  name: string;
  description: string;
}


export const PlaylistList: React.FC<PlaylistListProps> = ({
  playlists,
  tracks,
  onUpdate,
  onDelete,
  onCreate,
}) => {
  const { t } = useTranslation('media');
  const { showSuccess, showError } = useToast();

  const [formOpen, setFormOpen] = useState(false);
  const [editingPlaylist, setEditingPlaylist] = useState<Playlist | null>(null);
  const [formData, setFormData] = useState<PlaylistFormData>({ name: '', description: '' });
  const [deleteTarget, setDeleteTarget] = useState<Playlist | null>(null);
  const [loading, setLoading] = useState(false);
  const [tracksDialogPlaylist, setTracksDialogPlaylist] = useState<PlaylistDetail | null>(null);
  const coverInputRef = useRef<HTMLInputElement>(null);
  const [coverTargetId, setCoverTargetId] = useState<number | null>(null);

  const handleOpenCreate = () => {
    setEditingPlaylist(null);
    setFormData({ name: '', description: '' });
    setFormOpen(true);
  };

  const handleOpenEdit = (pl: Playlist) => {
    setEditingPlaylist(pl);
    setFormData({ name: pl.name, description: pl.description ?? '' });
    setFormOpen(true);
  };

  const handleSave = async () => {
    if (!formData.name.trim()) return;
    setLoading(true);
    try {
      if (editingPlaylist) {
        const updated = await playlistsApi.update(editingPlaylist.id, {
          name: formData.name.trim(),
          description: formData.description.trim() || null,
        });
        onUpdate(updated);
        showSuccess(t('playlists.updated', { defaultValue: 'Playlist aktualisiert' }));
      } else {
        const created = await playlistsApi.create({
          name: formData.name.trim(),
          description: formData.description.trim() || null,
        });
        onCreate(created);
        showSuccess(t('playlists.created', { defaultValue: 'Playlist erstellt' }));
      }
      setFormOpen(false);
    } catch {
      showError(t('playlists.save_error', { defaultValue: 'Playlist konnte nicht gespeichert werden' }));
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteConfirm = async () => {
    if (!deleteTarget) return;
    try {
      await playlistsApi.delete(deleteTarget.id);
      onDelete(deleteTarget);
      showSuccess(t('playlists.deleted', { defaultValue: 'Playlist gelöscht' }));
    } catch {
      showError(t('playlists.delete_error', { defaultValue: 'Playlist konnte nicht gelöscht werden' }));
    } finally {
      setDeleteTarget(null);
    }
  };

  const handleOpenTracksDialog = async (pl: Playlist) => {
    try {
      const detail = await playlistsApi.getById(pl.id);
      setTracksDialogPlaylist(detail);
    } catch {
      showError(t('playlists.load_error', { defaultValue: 'Tracks konnten nicht geladen werden' }));
    }
  };

  const handleCoverUpload = async (file: File) => {
    if (coverTargetId === null) return;
    try {
      const updated = await playlistsApi.uploadCover(coverTargetId, file);
      onUpdate(updated);
      showSuccess(t('playlists.cover_uploaded', { defaultValue: 'Cover hochgeladen' }));
    } catch {
      showError(t('playlists.cover_error', { defaultValue: 'Cover konnte nicht hochgeladen werden' }));
    } finally {
      setCoverTargetId(null);
    }
  };

  const handlePlay = (pl: Playlist) => {
    audioApi.play({ playlist_id: pl.id }).catch(() =>
      showError(t('playlists.play_error', { defaultValue: 'Playlist konnte nicht abgespielt werden' }))
    );
  };

  return (
    <Box>
      <Box display="flex" justifyContent="flex-end" mb={2}>
        <Button variant="contained" startIcon={<AddIcon />} onClick={handleOpenCreate}>
          {t('playlists.create')}
        </Button>
      </Box>

      {playlists.length === 0 ? (
        <Box display="flex" justifyContent="center" py={6}>
          <Typography color="text.secondary">{t('playlists.no_playlists')}</Typography>
        </Box>
      ) : (
        <>
          <Grid container spacing={2}>
            {playlists.map((pl) => (
              <Grid item xs={12} sm={6} md={4} key={pl.id}>
                <Card
                  variant="outlined"
                  sx={{ borderRadius: 2, height: '100%', display: 'flex', flexDirection: 'column' }}
                >
                  {/* Cover Art */}
                  {pl.cover_art_url ? (
                    <CardMedia
                      component="img"
                      height="120"
                      image={pl.cover_art_url}
                      alt={pl.name}
                      sx={{ objectFit: 'cover' }}
                    />
                  ) : (
                    <Box
                      sx={{
                        height: 80,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        bgcolor: 'action.hover',
                        cursor: 'pointer',
                      }}
                      onClick={() => { setCoverTargetId(pl.id); coverInputRef.current?.click(); }}
                      title={t('playlists.upload_cover')}
                    >
                      <ImageIcon sx={{ color: 'text.disabled', fontSize: 32 }} />
                    </Box>
                  )}

                  <CardContent sx={{ pb: 0, flex: 1 }}>
                    <Typography
                      variant="subtitle1"
                      fontWeight={600}
                      display="flex"
                      alignItems="center"
                      gap={1}
                    >
                      <PlaylistPlayIcon fontSize="small" color="primary" />
                      {pl.name}
                    </Typography>
                    {pl.description && (
                      <Typography
                        variant="body2"
                        color="text.secondary"
                        sx={{
                          mt: 0.5,
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {pl.description}
                      </Typography>
                    )}
                    {pl.tracks !== undefined && (
                      <Chip
                        label={`${pl.tracks.length} ${t('playlists.track_count_label')}`}
                        size="small"
                        variant="outlined"
                        sx={{ mt: 1 }}
                      />
                    )}
                  </CardContent>

                  <CardActions sx={{ pt: 0 }}>
                    <Tooltip title={t('playlists.play')}>
                      <IconButton size="small" color="primary" onClick={() => handlePlay(pl)}>
                        <PlayArrowIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                    <Tooltip title={t('playlists.edit_tracks')}>
                      <IconButton size="small" onClick={() => handleOpenTracksDialog(pl)}>
                        <QueueMusicIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                    <Tooltip title={t('playlists.upload_cover')}>
                      <IconButton
                        size="small"
                        onClick={() => { setCoverTargetId(pl.id); coverInputRef.current?.click(); }}
                      >
                        <UploadIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                    <Tooltip title={t('playlists.edit')}>
                      <IconButton size="small" onClick={() => handleOpenEdit(pl)}>
                        <EditIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                    <Tooltip title={t('playlists.delete')}>
                      <IconButton size="small" color="error" onClick={() => setDeleteTarget(pl)}>
                        <DeleteIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  </CardActions>
                </Card>
              </Grid>
            ))}
          </Grid>

          {/* Hidden cover file input */}
          <input
            ref={coverInputRef}
            type="file"
            accept="image/*"
            style={{ display: 'none' }}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) handleCoverUpload(f);
              e.target.value = '';
            }}
          />
        </>
      )}

      {/* Create / Edit Dialog */}
      <Dialog open={formOpen} onClose={() => setFormOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle sx={{ fontSize: '1.25rem', fontWeight: 600 }}>
          {editingPlaylist ? t('playlists.edit') : t('playlists.create')}
        </DialogTitle>
        <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: '16px !important' }}>
          <TextField
            label={t('playlists.fields.name')}
            placeholder={t('playlists.fields.name_placeholder')}
            value={formData.name}
            onChange={(e) => setFormData((p) => ({ ...p, name: e.target.value }))}
            fullWidth
            size="small"
            required
          />
          <TextField
            label={t('playlists.fields.description')}
            placeholder={t('playlists.fields.description_placeholder')}
            value={formData.description}
            onChange={(e) => setFormData((p) => ({ ...p, description: e.target.value }))}
            fullWidth
            size="small"
            multiline
            rows={2}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setFormOpen(false)}>
            {t('cancel', { ns: 'common' })}
          </Button>
          <Button
            onClick={handleSave}
            variant="contained"
            disabled={!formData.name.trim() || loading}
          >
            {t('save', { ns: 'common' })}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Tracks Dialog */}
      <PlaylistTracksDialog
        open={!!tracksDialogPlaylist}
        playlist={tracksDialogPlaylist}
        allTracks={tracks}
        onClose={() => setTracksDialogPlaylist(null)}
        onSaved={(updated) => {
          onUpdate(updated);
          showSuccess(t('playlists.tracks_saved', { defaultValue: 'Tracks gespeichert' }));
        }}
      />

      {/* Delete Confirmation */}
      <Dialog open={!!deleteTarget} onClose={() => setDeleteTarget(null)}>
        <DialogTitle sx={{ fontSize: '1.25rem', fontWeight: 600 }}>
          {t('playlists.delete')}
        </DialogTitle>
        <DialogContent>
          <DialogContentText>
            {t('playlists.delete_confirm', { name: deleteTarget?.name })}
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteTarget(null)}>
            {t('cancel', { ns: 'common' })}
          </Button>
          <Button onClick={handleDeleteConfirm} color="error" variant="contained">
            {t('delete', { ns: 'common' })}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};
