import React, { useState } from 'react';
import {
  Avatar,
  Box,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  IconButton,
  List,
  ListItemButton,
  ListItemAvatar,
  ListItemText,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import PlaylistPlayIcon from '@mui/icons-material/PlaylistPlay';
import { useTranslation } from 'react-i18next';
import { playlistsApi } from '@/api/playlists';
import { useToast } from '@/contexts/ToastContext';
import { ActionButton } from '@/components/ui/ActionButton';
import { CoverUploadField } from '@/components/media/CoverUploadField';
import type { Playlist, Track, Stream } from '@/types/api';

type View = 'list' | 'create';

interface AddToPlaylistDialogProps {
  open: boolean;
  track: Track | Stream | null;
  playlists: Playlist[];
  onClose: () => void;
  /** Called with the updated playlist after a track was added to an existing playlist */
  onAdded?: (playlist: Playlist) => void;
  /** Called with the newly created playlist (before track was appended) */
  onCreated?: (playlist: Playlist) => void;
}

export const AddToPlaylistDialog: React.FC<AddToPlaylistDialogProps> = ({
  open,
  track,
  playlists,
  onClose,
  onAdded,
  onCreated,
}) => {
  const { t } = useTranslation('media');
  const { showSuccess, showError } = useToast();

  const [view, setView] = useState<View>('list');
  const [loadingId, setLoadingId] = useState<number | null>(null);

  // Create-form state
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [coverFile, setCoverFile] = useState<File | null>(null);
  const [saving, setSaving] = useState(false);

  const resetCreateForm = () => {
    setName('');
    setDescription('');
    setCoverFile(null);
  };

  const handleClose = () => {
    setView('list');
    resetCreateForm();
    onClose();
  };

  const handleAdd = async (playlist: Playlist) => {
    if (!track) return;
    setLoadingId(playlist.id);
    try {
      const updated = await playlistsApi.appendTrack(playlist.id, track.id);
      showSuccess(
        t('playlists.track_added', {
          defaultValue: '"{{track}}" zu "{{playlist}}" hinzugef\u00fcgt',
          track: track.title,
          playlist: playlist.name,
        })
      );
      onAdded?.(updated);
      handleClose();
    } catch {
      showError(
        t('playlists.track_add_error', { defaultValue: 'Track konnte nicht hinzugef\u00fcgt werden' })
      );
    } finally {
      setLoadingId(null);
    }
  };

  const handleCreate = async () => {
    if (!name.trim() || !track) return;
    setSaving(true);
    try {
      // 1. Create playlist
      let created = await playlistsApi.create({
        name: name.trim(),
        description: description.trim() || null,
      });
      // 2. Upload cover if chosen
      if (coverFile) {
        created = await playlistsApi.uploadCover(created.id, coverFile);
      }
      onCreated?.(created);
      // 3. Append track
      const updated = await playlistsApi.appendTrack(created.id, track.id);
      showSuccess(
        t('playlists.track_added', {
          defaultValue: '"{{track}}" zu "{{playlist}}" hinzugef\u00fcgt',
          track: track.title,
          playlist: created.name,
        })
      );
      onAdded?.(updated);
      handleClose();
    } catch {
      showError(
        t('playlists.save_error', { defaultValue: 'Playlist konnte nicht gespeichert werden' })
      );
    } finally {
      setSaving(false);
    }
  };

  if (!track) return null;

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="xs" fullWidth>
      {/* ── Header ── */}
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1, fontWeight: 600, fontSize: '1rem', pb: 0.5 }}>
        {view === 'create' && (
          <Tooltip title={t('back', { ns: 'common', defaultValue: 'Zur\u00fcck' })}>
            <IconButton size="small" onClick={() => { setView('list'); resetCreateForm(); }} sx={{ mr: 0.5 }}>
              <ArrowBackIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        )}
        {view === 'list'
          ? t('playlists.add_to_playlist', { defaultValue: 'Zu Playlist hinzuf\u00fcgen' })
          : t('playlists.create', { defaultValue: 'Neue Playlist' })
        }
      </DialogTitle>

      {/* ── List view ── */}
      {view === 'list' && (
        <DialogContent sx={{ pt: '8px !important', px: 1 }}>
          <Typography variant="caption" color="text.secondary" sx={{ px: 1, display: 'block', mb: 0.5 }}>
            {track.title}
          </Typography>
          <Divider sx={{ mb: 0.5 }} />

          <List dense disablePadding>
            {playlists.map((pl) => (
              <ListItemButton
                key={pl.id}
                onClick={() => void handleAdd(pl)}
                disabled={loadingId !== null}
                sx={{ borderRadius: 1 }}
              >
                <ListItemAvatar sx={{ minWidth: 40 }}>
                  {pl.cover_art_url ? (
                    <Avatar src={pl.cover_art_url} variant="rounded" sx={{ width: 32, height: 32 }} />
                  ) : (
                    <Avatar variant="rounded" sx={{ width: 32, height: 32, bgcolor: 'secondary.main' }}>
                      <PlaylistPlayIcon sx={{ fontSize: 16 }} />
                    </Avatar>
                  )}
                </ListItemAvatar>
                <ListItemText
                  primary={
                    <Typography variant="body2" noWrap fontWeight={500}>
                      {pl.name}
                    </Typography>
                  }
                />
                {loadingId === pl.id && (
                  <CircularProgress size={16} sx={{ ml: 1, flexShrink: 0 }} />
                )}
              </ListItemButton>
            ))}

            {/* Neue Playlist anlegen */}
            <Divider sx={{ my: 0.5 }} />
            <ListItemButton
              onClick={() => setView('create')}
              disabled={loadingId !== null}
              sx={{ borderRadius: 1, color: 'primary.main' }}
            >
              <ListItemAvatar sx={{ minWidth: 40 }}>
                <Avatar variant="rounded" sx={{ width: 32, height: 32, bgcolor: 'primary.main' }}>
                  <AddIcon sx={{ fontSize: 16 }} />
                </Avatar>
              </ListItemAvatar>
              <ListItemText
                primary={
                  <Typography variant="body2" fontWeight={600} color="primary">
                    {t('playlists.create', { defaultValue: 'Neue Playlist' })}
                  </Typography>
                }
              />
            </ListItemButton>
          </List>
        </DialogContent>
      )}

      {/* ── Create view ── */}
      {view === 'create' && (
        <>
          <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: '16px !important' }}>
            <CoverUploadField
              displayUrl={coverFile ? URL.createObjectURL(coverFile) : null}
              coverFile={coverFile}
              onFileSelect={(file) => setCoverFile(file)}
              onRemove={() => setCoverFile(null)}
            />
            <TextField
              label={t('playlists.fields.name', { defaultValue: 'Name' })}
              placeholder={t('playlists.fields.name_placeholder', { defaultValue: 'Playlist-Name' })}
              value={name}
              onChange={(e) => setName(e.target.value)}
              fullWidth
              size="small"
              required
              autoFocus
            />
            <TextField
              label={t('playlists.fields.description', { defaultValue: 'Beschreibung' })}
              placeholder={t('playlists.fields.description_placeholder', { defaultValue: 'Optional\u2026' })}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              fullWidth
              size="small"
              multiline
              rows={2}
            />
          </DialogContent>
          <DialogActions>
            <ActionButton actionType="secondary" onClick={() => { setView('list'); resetCreateForm(); }}>
              {t('cancel', { ns: 'common', defaultValue: 'Abbrechen' })}
            </ActionButton>
            <ActionButton
              actionType="primary"
              onClick={handleCreate}
              disabled={!name.trim() || saving}
            >
              {saving ? <CircularProgress size={16} /> : t('save', { ns: 'common', defaultValue: 'Speichern' })}
            </ActionButton>
          </DialogActions>
        </>
      )}
    </Dialog>
  );
};
