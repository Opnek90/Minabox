import React, { useEffect, useMemo, useState } from 'react';
import {
  Box,
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
  Tooltip,
  Typography,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/Delete';
import DragIndicatorIcon from '@mui/icons-material/DragIndicator';
import SearchIcon from '@mui/icons-material/Search';
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  DragEndEvent,
} from '@dnd-kit/core';
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { useTranslation } from 'react-i18next';
import { useToast } from '@/contexts/ToastContext';
import { playlistsApi } from '@/api/playlists';
import type { PlaylistDetail, Playlist, Track } from '@/types/api';


// ── Sortable Track Item ───────────────────────────────────────────────────────
interface SortableTrackItemProps {
  id: string;
  track: Track | undefined;
  onRemove: () => void;
}

const SortableTrackItem: React.FC<SortableTrackItemProps> = ({ id, track, onRemove }) => {
  const { t } = useTranslation('media');
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id });

  const style: React.CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.4 : 1,
    zIndex: isDragging ? 999 : 'auto',
    position: 'relative',
  };

  return (
    <ListItem
      ref={setNodeRef}
      style={style}
      sx={{
        borderRadius: 1,
        mb: 0.5,
        border: '1px solid',
        borderColor: isDragging ? 'primary.main' : 'divider',
        bgcolor: 'background.paper',
        pr: 6,
        pl: 0.5,
        transition: 'border-color 0.15s',
      }}
      secondaryAction={
        <IconButton edge="end" size="small" onClick={onRemove} aria-label={t('playlists.remove_track')}>
          <DeleteIcon fontSize="small" />
        </IconButton>
      }
    >
      <Box
        {...attributes}
        {...listeners}
        sx={{
          display: 'flex',
          alignItems: 'center',
          cursor: isDragging ? 'grabbing' : 'grab',
          color: 'text.disabled',
          px: 0.75,
          flexShrink: 0,
          touchAction: 'none',
          '&:hover': { color: 'text.secondary' },
        }}
        aria-label="Drag to reorder"
      >
        <DragIndicatorIcon fontSize="small" />
      </Box>
      <ListItemText
        primary={
          <Typography variant="body2" fontWeight={500} noWrap>
            {track?.title ?? `ID ${id}`}
          </Typography>
        }
        secondary={
          <Typography variant="caption" color="text.secondary" noWrap>
            {track?.artist ?? track?.source_type ?? ''}
          </Typography>
        }
      />
    </ListItem>
  );
};


// ── Dialog ───────────────────────────────────────────────────────────────────
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
  const { showError } = useToast();
  const [trackIds, setTrackIds] = useState<number[]>([]);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  );

  useEffect(() => {
    if (playlist?.tracks) {
      setTrackIds(playlist.tracks.map((tr) => tr.id));
    } else {
      setTrackIds([]);
    }
    setSearchQuery('');
  }, [playlist, open]);

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    setTrackIds((prev) => {
      const oldIndex = prev.indexOf(Number(active.id));
      const newIndex = prev.indexOf(Number(over.id));
      return arrayMove(prev, oldIndex, newIndex);
    });
  };

  const handleRemove = (trackId: number) => {
    setTrackIds((prev) => prev.filter((id) => id !== trackId));
  };

  const handleAddTrack = (trackId: number) => {
    setTrackIds((prev) => [...prev, trackId]);
    setSearchQuery('');
  };

  const handleSave = async () => {
    if (!playlist) return;
    setLoading(true);
    try {
      const updated = await playlistsApi.update(playlist.id, { track_ids: trackIds });
      onSaved(updated);
      onClose();
    } catch {
      showError(t('playlists.tracks_save_error', { defaultValue: 'Tracks konnten nicht gespeichert werden' }));
    } finally {
      setLoading(false);
    }
  };

  const trackMap = useMemo(
    () => new Map(allTracks.map((tr) => [tr.id, tr])),
    [allTracks]
  );

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

  const sortableIds = trackIds.map(String);

  if (!playlist) return null;

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ fontSize: '1.25rem', fontWeight: 600 }}>
        {t('playlists.add_tracks')} – {playlist.name}
      </DialogTitle>

      <DialogContent dividers sx={{ pt: 1 }}>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
          {t('playlists.track_count_plural', { count: trackIds.length })}
        </Typography>

        {/* ── Sortable track list ───────────────────────────────────── */}
        {trackIds.length === 0 ? (
          <Typography variant="body2" color="text.disabled" sx={{ py: 1, textAlign: 'center' }}>
            {t('playlists.no_tracks', { defaultValue: 'Noch keine Tracks.' })}
          </Typography>
        ) : (
          <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
            <SortableContext items={sortableIds} strategy={verticalListSortingStrategy}>
              <List dense disablePadding sx={{ mb: 1 }}>
                {trackIds.map((id) => (
                  <SortableTrackItem
                    key={id}
                    id={String(id)}
                    track={trackMap.get(id) ?? playlist.tracks.find((tr) => tr.id === id)}
                    onRemove={() => handleRemove(id)}
                  />
                ))}
              </List>
            </SortableContext>
          </DndContext>
        )}

        {/* ── Add tracks ───────────────────────────────────────────── */}
        {availableTracks.length > 0 && (
          <>
            <Typography variant="subtitle2" sx={{ mt: 2, mb: 1 }}>
              {t('playlists.edit_tracks_add')}
            </Typography>
            <TextField
              fullWidth size="small"
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
            <List dense disablePadding sx={{ maxHeight: 240, overflow: 'auto' }}>
              {filteredAvailable.map((track) => (
                <ListItem
                  key={track.id}
                  sx={{ borderRadius: 1, mb: 0.25, '&:hover': { bgcolor: 'action.hover' } }}
                  secondaryAction={
                    <Tooltip title={t('add', { ns: 'common' })}>
                      <IconButton size="small" onClick={() => handleAddTrack(track.id)}>
                        <AddIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  }
                >
                  <ListItemText
                    primary={<Typography variant="body2" noWrap>{track.title}</Typography>}
                    secondary={
                      <Typography variant="caption" color="text.secondary" noWrap>
                        {track.artist ?? track.source_type}
                      </Typography>
                    }
                  />
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
