import React, { useRef, useState } from 'react';
import {
  Box,
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
  Divider,
  Grid,
  IconButton,
  List,
  ListItem,
  ListItemAvatar,
  ListItemText,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Tooltip,
  Typography,
} from '@mui/material';
import ViewListIcon from '@mui/icons-material/ViewList';
import ViewModuleIcon from '@mui/icons-material/ViewModule';
import PlaylistAddIcon from '@mui/icons-material/PlaylistAdd';
import EditIcon from '@mui/icons-material/Edit';
import DeleteIcon from '@mui/icons-material/Delete';
import PlaylistPlayIcon from '@mui/icons-material/PlaylistPlay';
import QueueMusicIcon from '@mui/icons-material/QueueMusic';
import UploadIcon from '@mui/icons-material/Upload';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import { useTranslation } from 'react-i18next';
import { useToast } from '@/contexts/ToastContext';
import type { Playlist, PlaylistDetail, Track } from '@/types/api';
import { playlistsApi } from '@/api/playlists';
import { audioApi } from '@/api/audio';
import { ActionButton } from '@/components/ui/ActionButton';
import { CoverUploadField } from './CoverUploadField';
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
  coverFile: File | null;
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
  const [formData, setFormData] = useState<PlaylistFormData>({ name: '', description: '', coverFile: null });
  const [deleteTarget, setDeleteTarget] = useState<Playlist | null>(null);
  const [loading, setLoading] = useState(false);
  const [tracksDialogPlaylist, setTracksDialogPlaylist] = useState<PlaylistDetail | null>(null);
  const coverInputRef = useRef<HTMLInputElement>(null);
  const [coverTargetId, setCoverTargetId] = useState<number | null>(null);
  const [viewMode, setViewMode] = useState<'card' | 'list'>('card');

  const handleOpenCreate = () => {
    setEditingPlaylist(null);
    setFormData({ name: '', description: '', coverFile: null });
    setFormOpen(true);
  };

  const handleOpenEdit = (pl: Playlist) => {
    setEditingPlaylist(pl);
    setFormData({ name: pl.name, description: pl.description ?? '', coverFile: null });
    setFormOpen(true);
  };

  const handleClearCoverInForm = () => {
    setFormData((p) => ({ ...p, coverFile: null }));
  };

  const handleRemoveCoverInForm = () => {
    if (formData.coverFile) {
      setFormData((p) => ({ ...p, coverFile: null }));
      return;
    }
    if (editingPlaylist?.cover_art_url) {
      playlistsApi
        .deleteCover(editingPlaylist.id)
        .then((updated) => {
          onUpdate(updated);
          setEditingPlaylist(updated);
        })
        .catch(() => showError(t('playlists.cover_error', { defaultValue: 'Cover konnte nicht entfernt werden' })));
    }
  };

  const handleSave = async () => {
    if (!formData.name.trim()) return;
    setLoading(true);
    try {
      if (editingPlaylist) {
        let updated = await playlistsApi.update(editingPlaylist.id, {
          name: formData.name.trim(),
          description: formData.description.trim() || null,
        });
        if (formData.coverFile) {
          updated = await playlistsApi.uploadCover(editingPlaylist.id, formData.coverFile);
        }
        onUpdate(updated);
        showSuccess(t('playlists.updated', { defaultValue: 'Playlist aktualisiert' }));
      } else {
        const created = await playlistsApi.create({
          name: formData.name.trim(),
          description: formData.description.trim() || null,
        });
        if (formData.coverFile) {
          const withCover = await playlistsApi.uploadCover(created.id, formData.coverFile);
          onCreate(withCover);
        } else {
          onCreate(created);
        }
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
      <Box display="flex" alignItems="center" justifyContent="space-between" mb={2} flexWrap="wrap" gap={1}>
        <ToggleButtonGroup
          value={viewMode}
          exclusive
          onChange={(_, v) => v && setViewMode(v)}
          size="small"
        >
          <ToggleButton value="card" aria-label={t('view_mode_card')}>
            <ViewModuleIcon />
          </ToggleButton>
          <ToggleButton value="list" aria-label={t('view_mode_list')}>
            <ViewListIcon />
          </ToggleButton>
        </ToggleButtonGroup>
        <ActionButton
          actionType="primary"
          startIcon={<PlaylistAddIcon />}
          onClick={handleOpenCreate}
        >
          {t('playlists.add_playlist')}
        </ActionButton>
      </Box>

      {playlists.length === 0 ? (
        <Box display="flex" justifyContent="center" py={6}>
          <Typography color="text.secondary">{t('playlists.no_playlists')}</Typography>
        </Box>
      ) : viewMode === 'list' ? (
        <List dense>
          {playlists.map((pl, idx) => (
            <React.Fragment key={pl.id}>
              {idx > 0 && <Divider component="li" />}
              <ListItem
                secondaryAction={
                  <Box>
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
                  </Box>
                }
              >
                <ListItemAvatar sx={{ minWidth: 52 }}>
                  {pl.cover_art_url ? (
                    <Box
                      component="img"
                      src={pl.cover_art_url}
                      alt=""
                      sx={{ width: 40, height: 40, objectFit: 'cover', borderRadius: 1 }}
                    />
                  ) : (
                    <Box
                      sx={{
                        width: 40,
                        height: 40,
                        borderRadius: 1,
                        bgcolor: 'action.hover',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                      }}
                    >
                      <PlaylistPlayIcon sx={{ color: 'text.disabled', fontSize: 24 }} />
                    </Box>
                  )}
                </ListItemAvatar>
                <ListItemText
                  primary={pl.name}
                  secondary={pl.description ?? (pl.tracks !== undefined ? `${pl.tracks.length} ${t('playlists.track_count_label')}` : null)}
                  primaryTypographyProps={{ fontWeight: 600 }}
                />
              </ListItem>
            </React.Fragment>
          ))}
        </List>
      ) : (
        <>
          <Grid container spacing={2}>
            {playlists.map((pl) => (
              <Grid item xs={12} sm={6} md={4} key={pl.id}>
                <Card
                  variant="outlined"
                  sx={{ borderRadius: 2, height: '100%', display: 'flex', flexDirection: 'column' }}
                >
                  {pl.cover_art_url && (
                    <CardMedia
                      component="img"
                      height="120"
                      image={pl.cover_art_url}
                      alt={pl.name}
                      sx={{ objectFit: 'cover' }}
                    />
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

        </>
      )}

      {playlists.length > 0 && (
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
      )}

      {/* Create / Edit Dialog */}
      <Dialog open={formOpen} onClose={() => setFormOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle sx={{ fontSize: '1.25rem', fontWeight: 600 }}>
          {editingPlaylist ? t('playlists.edit') : t('playlists.create')}
        </DialogTitle>
        <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: '16px !important' }}>
          <CoverUploadField
            displayUrl={
              formData.coverFile
                ? URL.createObjectURL(formData.coverFile)
                : editingPlaylist?.cover_art_url ?? null
            }
            coverFile={formData.coverFile}
            onFileSelect={(file) => setFormData((p) => ({ ...p, coverFile: file }))}
            onRemove={editingPlaylist ? handleRemoveCoverInForm : handleClearCoverInForm}
          />
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
          <ActionButton actionType="secondary" onClick={() => setFormOpen(false)}>
            {t('cancel', { ns: 'common' })}
          </ActionButton>
          <ActionButton
            actionType="primary"
            onClick={handleSave}
            disabled={!formData.name.trim() || loading}
          >
            {t('save', { ns: 'common' })}
          </ActionButton>
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
          <ActionButton actionType="secondary" onClick={() => setDeleteTarget(null)}>
            {t('cancel', { ns: 'common' })}
          </ActionButton>
          <ActionButton actionType="destructive" onClick={handleDeleteConfirm}>
            {t('delete', { ns: 'common' })}
          </ActionButton>
        </DialogActions>
      </Dialog>
    </Box>
  );
};
