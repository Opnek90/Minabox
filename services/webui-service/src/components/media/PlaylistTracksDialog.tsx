import React, { useEffect, useMemo, useState } from 'react';
import {
  Box,
  Button,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  InputAdornment,
  List,
  ListItem,
  ListItemText,
  Tab,
  Tabs,
  TextField,
  Tooltip,
  Typography,
  useMediaQuery,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import ArrowDownwardIcon from '@mui/icons-material/ArrowDownward';
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward';
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
import { ResponsiveDialog } from '@/components/common/ResponsiveDialog';


// ── Sortable Track Item ───────────────────────────────────────────────────────
interface SortableTrackItemProps {
  id: string;
  track: Track | undefined;
  onRemove: () => void;
  /** Touch devices sort via arrow buttons instead of drag. */
  useArrows: boolean;
  onMoveUp: () => void;
  onMoveDown: () => void;
  isFirst: boolean;
  isLast: boolean;
}

const SortableTrackItem: React.FC<SortableTrackItemProps> = ({
  id,
  track,
  onRemove,
  useArrows,
  onMoveUp,
  onMoveDown,
  isFirst,
  isLast,
}) => {
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
        // Room for the actions on the right: on touch it is three buttons
        // (up/down/remove) at 44px, otherwise just the remove button.
        pr: useArrows ? 18 : 6,
        pl: 0.5,
        transition: 'border-color 0.15s',
      }}
      secondaryAction={
        <>
          {useArrows && (
            <>
              <IconButton
                size="small"
                onClick={onMoveUp}
                disabled={isFirst}
                aria-label={t('playlists.move_up')}
              >
                <ArrowUpwardIcon fontSize="small" />
              </IconButton>
              <IconButton
                size="small"
                onClick={onMoveDown}
                disabled={isLast}
                aria-label={t('playlists.move_down')}
              >
                <ArrowDownwardIcon fontSize="small" />
              </IconButton>
            </>
          )}
          <IconButton edge="end" size="small" onClick={onRemove} aria-label={t('playlists.remove_track')}>
            <DeleteIcon fontSize="small" />
          </IconButton>
        </>
      }
    >
      {/* The drag handle is only ~20px wide - not reliably hit with a finger,
          and a drag over 30 positions in a scrolling sheet is not workable
          anyway. Touch therefore gets the arrow buttons. */}
      {!useArrows && (
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
      )}
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
  const { t } = useTranslation(['media', 'common']);
  const { showError } = useToast();
  const [trackIds, setTrackIds] = useState<number[]>([]);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [tab, setTab] = useState(0);
  // On touch devices, sorting is via arrow buttons instead of drag.
  const useArrows = useMediaQuery('(pointer: coarse)');

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
    setTab(0);
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

  const handleMove = (index: number, delta: number) => {
    setTrackIds((prev) => {
      const target = index + delta;
      if (target < 0 || target >= prev.length) return prev;
      return arrayMove(prev, index, target);
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
      showError(t('playlists.tracks_save_error'));
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
    <ResponsiveDialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ fontSize: '1.25rem', fontWeight: 600 }}>
        {t('playlists.add_tracks')} – {playlist.name}
      </DialogTitle>

      {/* Two tabs instead of order + search list stacked: three scroll
          containers used to nest (page > dialog > track list), and on the
          phone they compete for every swipe. */}
      <Tabs
        value={tab}
        onChange={(_, value: number) => setTab(value)}
        variant="fullWidth"
        sx={{ borderBottom: 1, borderColor: 'divider', flexShrink: 0 }}
      >
        <Tab label={t('playlists.track_order')} />
        <Tab label={t('playlists.add_tracks')} />
      </Tabs>

      <DialogContent dividers sx={{ pt: 1 }}>
        {tab === 0 && (
          <>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
              {t('playlists.track_count', { count: trackIds.length })}
            </Typography>

            {trackIds.length === 0 ? (
              <Typography variant="body2" color="text.secondary" sx={{ py: 1, textAlign: 'center' }}>
                {t('playlists.no_tracks')}
              </Typography>
            ) : (
              <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
                <SortableContext items={sortableIds} strategy={verticalListSortingStrategy}>
                  <List dense disablePadding sx={{ mb: 1 }}>
                    {trackIds.map((id, index) => (
                      <SortableTrackItem
                        key={id}
                        id={String(id)}
                        track={trackMap.get(id) ?? playlist.tracks.find((tr) => tr.id === id)}
                        onRemove={() => handleRemove(id)}
                        useArrows={useArrows}
                        onMoveUp={() => handleMove(index, -1)}
                        onMoveDown={() => handleMove(index, 1)}
                        isFirst={index === 0}
                        isLast={index === trackIds.length - 1}
                      />
                    ))}
                  </List>
                </SortableContext>
              </DndContext>
            )}
          </>
        )}

        {tab === 1 && (
          <>
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
            {availableTracks.length === 0 ? (
              <Typography variant="body2" color="text.secondary" sx={{ py: 1, textAlign: 'center' }}>
                {t('playlists.edit_tracks_no_match')}
              </Typography>
            ) : (
              <List dense disablePadding>
                {filteredAvailable.map((track) => (
                  <ListItem
                    key={track.id}
                    sx={{ borderRadius: 1, mb: 0.25, '&:hover': { bgcolor: 'action.hover' } }}
                    secondaryAction={
                      <Tooltip title={t('common:actions.add')}>
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
            )}
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
    </ResponsiveDialog>
  );
};
