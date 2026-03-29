import React, { useState } from 'react';
import {
  Avatar,
  Box,
  CircularProgress,
  Dialog,
  DialogContent,
  DialogTitle,
  Divider,
  List,
  ListItemButton,
  ListItemAvatar,
  ListItemText,
  Typography,
} from '@mui/material';
import PlaylistPlayIcon from '@mui/icons-material/PlaylistPlay';
import { useTranslation } from 'react-i18next';
import { playlistsApi } from '@/api/playlists';
import { useToast } from '@/contexts/ToastContext';
import type { Playlist, Track, Stream } from '@/types/api';

interface AddToPlaylistDialogProps {
  open: boolean;
  track: Track | Stream | null;
  playlists: Playlist[];
  onClose: () => void;
  /** Called with the updated playlist after a successful add */
  onAdded?: (playlist: Playlist) => void;
}

export const AddToPlaylistDialog: React.FC<AddToPlaylistDialogProps> = ({
  open,
  track,
  playlists,
  onClose,
  onAdded,
}) => {
  const { t } = useTranslation('media');
  const { showSuccess, showError } = useToast();
  const [loadingId, setLoadingId] = useState<number | null>(null);

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
      onClose();
    } catch {
      showError(
        t('playlists.track_add_error', { defaultValue: 'Track konnte nicht hinzugef\u00fcgt werden' })
      );
    } finally {
      setLoadingId(null);
    }
  };

  if (!track) return null;

  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle sx={{ fontWeight: 600, fontSize: '1rem', pb: 0.5 }}>
        {t('playlists.add_to_playlist', { defaultValue: 'Zu Playlist hinzuf\u00fcgen' })}
      </DialogTitle>
      <DialogContent sx={{ pt: '8px !important', px: 1 }}>
        <Typography variant="caption" color="text.secondary" sx={{ px: 1, display: 'block', mb: 0.5 }}>
          {track.title}
        </Typography>
        <Divider sx={{ mb: 0.5 }} />
        {playlists.length === 0 ? (
          <Typography variant="body2" color="text.secondary" sx={{ py: 2, textAlign: 'center' }}>
            {t('playlists.no_playlists', { defaultValue: 'Keine Playlists vorhanden' })}
          </Typography>
        ) : (
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
          </List>
        )}
      </DialogContent>
    </Dialog>
  );
};
