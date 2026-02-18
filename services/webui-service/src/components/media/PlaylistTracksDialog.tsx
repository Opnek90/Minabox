import React, { useEffect, useMemo, useState } from 'react';
import {
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  InputAdornment,
  List,
  ListItem,
  ListItemText,
  TextField,
  Typography,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/Delete';
import SearchIcon from '@mui/icons-material/Search';
import { useTranslation } from 'react-i18next';
import { playlistsApi } from '@/api/playlists';
import type { PlaylistDetail, Playlist, Track } from '@/types/api';

interface PlaylistTracksDialogProps {
  open: boolean;
  playlist: PlaylistDetail | null;
  allTracks: Track[];
  onClose: () => void;
  onSaved: (playlist: Playlist) => void;
}

export const PlaylistTracksDialog: React.FC<PlaylistTracksDialogProps> = ({
  open,
  playlist,
  allTracks,
  onClose,
  onSaved,
}) => {
  const { t } = useTranslation('media');
  const [trackIds, setTrackIds] = useState<number[]>([]);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    if (playlist?.tracks) {
      setTrackIds(playlist.tracks.map((t) => t.id));
    } else {
      setTrackIds([]);
    }
  }, [playlist, open]);

  const handleRemove = (trackId: number) => {
    setTrackIds((prev) => prev.filter((id) => id !== trackId));
  };

  const handleAddTrack = (trackId: number) => {
    setTrackIds((prev) => [...prev, trackId]);
  };

  const handleSave = async () => {
    if (!playlist) return;
    setLoading(true);
    try {
      const updated = await playlistsApi.update(playlist.id, { track_ids: trackIds });
      onSaved(updated);
      onClose();
    } finally {
      setLoading(false);
    }
  };

  const currentTrackIdsSet = new Set(trackIds);
  const availableTracks = allTracks.filter((tr) => !currentTrackIdsSet.has(tr.id));

  const searchLower = searchQuery.trim().toLowerCase();
  const filteredAvailable = useMemo(() => {
    if (!searchLower) return availableTracks;
    return availableTracks.filter(
      (tr) =>
        tr.title?.toLowerCase().includes(searchLower) ||
        tr.artist?.toLowerCase().includes(searchLower) ||
        tr.album?.toLowerCase().includes(searchLower)
    );
  }, [availableTracks, searchLower]);

  if (!playlist) return null;

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ fontSize: '1.25rem', fontWeight: 600 }}>
        {t('playlists.add_tracks')} – {playlist.name}
      </DialogTitle>
      <DialogContent dividers sx={{ pt: 1 }}>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
          {t('playlists.track_count_plural', { count: trackIds.length })}
        </Typography>
        <List dense disablePadding>
          {trackIds.map((id) => {
            const track = allTracks.find((t) => t.id === id) ?? playlist.tracks.find((t) => t.id === id);
            return (
              <ListItem
                key={id}
                secondaryAction={
                  <IconButton
                    edge="end"
                    size="small"
                    onClick={() => handleRemove(id)}
                    aria-label={t('playlists.remove_track')}
                  >
                    <DeleteIcon fontSize="small" />
                  </IconButton>
                }
              >
                <ListItemText
                  primary={track?.title ?? `ID ${id}`}
                  secondary={track?.artist ?? track?.source_type}
                />
              </ListItem>
            );
          })}
        </List>
        {availableTracks.length > 0 && (
          <>
            <Typography variant="subtitle2" sx={{ mt: 2, mb: 1 }}>
              {t('playlists.edit_tracks_add')}
            </Typography>
            <TextField
              fullWidth
              size="small"
              placeholder={t('track_selector.search_placeholder')}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <SearchIcon fontSize="small" />
                  </InputAdornment>
                ),
              }}
              sx={{ mb: 1 }}
            />
            <List dense disablePadding sx={{ maxHeight: 280, overflow: 'auto' }}>
              {filteredAvailable.map((track) => (
                <ListItem
                  key={track.id}
                  secondaryAction={
                    <Button
                      size="small"
                      startIcon={<AddIcon />}
                      onClick={() => handleAddTrack(track.id)}
                    >
                      {t('add', { ns: 'common' })}
                    </Button>
                  }
                >
                  <ListItemText primary={track.title} secondary={track.artist ?? track.source_type} />
                </ListItem>
              ))}
            </List>
            {searchLower && filteredAvailable.length === 0 && (
              <Typography variant="body2" color="text.secondary" sx={{ py: 1 }}>
                {t('playlists.edit_tracks_no_match')}
              </Typography>
            )}
          </>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('cancel', { ns: 'common' })}</Button>
        <Button onClick={handleSave} variant="contained" disabled={loading}>
          {t('save', { ns: 'common' })}
        </Button>
      </DialogActions>
    </Dialog>
  );
};
