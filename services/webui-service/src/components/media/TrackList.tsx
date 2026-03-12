import React, { useState } from 'react';
import {
  Avatar,
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
  Grid,
  IconButton,
  InputAdornment,
  ListItem,
  ListItemAvatar,
  ListItemText,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Tooltip,
  Typography,
} from '@mui/material';
import ArrowDownwardIcon from '@mui/icons-material/ArrowDownward';
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward';
import AudiotrackIcon from '@mui/icons-material/Audiotrack';
import DeleteIcon from '@mui/icons-material/Delete';
import EditIcon from '@mui/icons-material/Edit';
import LinkIcon from '@mui/icons-material/Link';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import SearchIcon from '@mui/icons-material/Search';
import ViewListIcon from '@mui/icons-material/ViewList';
import ViewModuleIcon from '@mui/icons-material/ViewModule';
import { useTranslation } from 'react-i18next';
import { Virtuoso, VirtuosoGrid } from 'react-virtuoso';
import { audioApi } from '@/api/audio';
import type { Track } from '@/types/api';
import { formatTime } from '@/utils/formatTime';
import { ActionButton } from '@/components/ui/ActionButton';


type SortKey = 'title' | 'artist' | 'duration_ms' | 'last_played_at';


interface TrackListProps {
  tracks: Track[];
  onDelete: (track: Track) => void;
  onEdit?: (track: Track) => void;
  selectionMode?: boolean;
  onSelect?: (track: Track) => void;
}


// Sub-components for VirtuosoGrid
const gridComponents = {
  List: React.forwardRef<HTMLDivElement>((props, ref) => (
    <Grid container spacing={2} {...props} ref={ref} />
  )),
  Item: ({ children, ...props }: any) => (
    <Grid item xs={12} sm={6} md={4} {...props}>
      {children}
    </Grid>
  )
};
gridComponents.List.displayName = 'GridList';


export const TrackList: React.FC<TrackListProps> = ({
  tracks,
  onDelete,
  onEdit,
  selectionMode = false,
  onSelect,
}) => {
  const { t } = useTranslation('media');
  const [search, setSearch] = useState('');
  const [filterSource, setFilterSource] = useState<'all' | 'file' | 'remote'>('all');
  const [trackToDelete, setTrackToDelete] = useState<Track | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>('title');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');
  const [viewMode, setViewMode] = useState<'card' | 'list'>('list');

  const filtered = tracks.filter((tr) => {
    const q = search.toLowerCase();
    const matchesSearch =
      tr.title.toLowerCase().includes(q) ||
      (tr.artist ?? '').toLowerCase().includes(q) ||
      (tr.album ?? '').toLowerCase().includes(q);
    const matchesFilter =
      filterSource === 'all' || tr.source_type === filterSource;
    return matchesSearch && matchesFilter;
  });

  const sorted = [...filtered].sort((a, b) => {
    let aVal: string | number;
    let bVal: string | number;
    if (sortKey === 'duration_ms') {
      aVal = a.duration_ms ?? 0;
      bVal = b.duration_ms ?? 0;
    } else if (sortKey === 'last_played_at') {
      aVal = a.last_played_at ? new Date(a.last_played_at).getTime() : 0;
      bVal = b.last_played_at ? new Date(b.last_played_at).getTime() : 0;
    } else if (sortKey === 'artist') {
      aVal = (a.artist ?? '').toLowerCase();
      bVal = (b.artist ?? '').toLowerCase();
    } else {
      aVal = a.title.toLowerCase();
      bVal = b.title.toLowerCase();
    }
    if (aVal < bVal) return sortDir === 'asc' ? -1 : 1;
    if (aVal > bVal) return sortDir === 'asc' ? 1 : -1;
    return 0;
  });

  const handleSortKey = (_: React.MouseEvent, key: SortKey | null) => {
    if (!key) return;
    if (key === sortKey) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir('asc');
    }
  };

  if (tracks.length === 0) {
    return (
      <Box display="flex" justifyContent="center" py={6}>
        <Typography color="text.secondary">{t('tracks.no_tracks')}</Typography>
      </Box>
    );
  }

  // Row renderer for standard list view
  const renderListItem = (index: number, track: Track) => (
    <ListItem
      key={track.id}
      divider={index < sorted.length - 1}
      secondaryAction={
        !selectionMode && (
          <Box>
            <Tooltip title={t('tracks.play')}>
              <IconButton
                size="small"
                color="primary"
                onClick={() => audioApi.play({ track_id: track.id })}
              >
                <PlayArrowIcon fontSize="small" />
              </IconButton>
            </Tooltip>
            {onEdit && (
              <Tooltip title={t('tracks.edit')}>
                <IconButton size="small" onClick={() => onEdit(track)}>
                  <EditIcon fontSize="small" />
                </IconButton>
              </Tooltip>
            )}
            <Tooltip title={t('tracks.delete')}>
              <IconButton
                size="small"
                color="error"
                onClick={() => setTrackToDelete(track)}
              >
                <DeleteIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          </Box>
        )
      }
      sx={
        selectionMode
          ? { cursor: 'pointer', '&:hover': { bgcolor: 'action.hover' } }
          : undefined
      }
      onClick={selectionMode && onSelect ? () => onSelect(track) : undefined}
    >
      <ListItemAvatar sx={{ minWidth: 44 }}>
        {track.cover_art_url ? (
          <Avatar
            src={track.cover_art_url}
            variant="rounded"
            sx={{ width: 40, height: 40 }}
          >
            <AudiotrackIcon />
          </Avatar>
        ) : (
          <Avatar variant="rounded" sx={{ width: 40, height: 40, bgcolor: 'action.selected' }}>
            {track.source_type === 'remote' ? (
              <LinkIcon fontSize="small" />
            ) : (
              <AudiotrackIcon fontSize="small" />
            )}
          </Avatar>
        )}
      </ListItemAvatar>
      <ListItemText
        primary={track.title}
        secondary={
          <Box
            component="span"
            display="flex"
            gap={1}
            alignItems="center"
            flexWrap="wrap"
          >
            {track.artist && (
              <Typography component="span" variant="caption">
                {track.artist}
              </Typography>
            )}
            {track.album && (
              <Typography component="span" variant="caption" color="text.disabled">
                · {track.album}
              </Typography>
            )}
            {track.duration_ms != null && (
              <Chip
                label={formatTime(track.duration_ms)}
                size="small"
                variant="outlined"
                sx={{ height: 18, fontSize: '0.65rem' }}
              />
            )}
            {track.last_played_at && (
              <Typography component="span" variant="caption" color="text.disabled">
                ·{' '}
                {new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' }).format(
                  -Math.round(
                    (Date.now() - new Date(track.last_played_at).getTime()) /
                      3_600_000
                  ),
                  'hour'
                )}
              </Typography>
            )}
          </Box>
        }
      />
    </ListItem>
  );

  // Item renderer for grid view
  const renderGridItem = (_index: number, track: Track) => (
    <Box sx={{ p: 1, height: '100%' }}>
      <Card
        variant="outlined"
        sx={{ borderRadius: 2, height: '100%', display: 'flex', flexDirection: 'column' }}
      >
        {track.cover_art_url && (
          <CardMedia
            component="img"
            height="120"
            image={track.cover_art_url}
            alt={track.title}
            sx={{ objectFit: 'cover' }}
          />
        )}
        <CardContent sx={{ pb: 0, flex: 1 }}>
          <Typography variant="subtitle1" fontWeight={600} display="flex" alignItems="center" gap={1}>
            {track.source_type === 'remote' ? (
              <LinkIcon fontSize="small" color="primary" />
            ) : (
              <AudiotrackIcon fontSize="small" color="primary" />
            )}
            {track.title}
          </Typography>
          {(track.artist || track.album) && (
            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }} noWrap>
              {[track.artist, track.album].filter(Boolean).join(' · ')}
            </Typography>
          )}
          {track.duration_ms != null && (
            <Chip
              label={formatTime(track.duration_ms)}
              size="small"
              variant="outlined"
              sx={{ mt: 1 }}
            />
          )}
        </CardContent>
        <CardActions sx={{ pt: 0 }}>
          {!selectionMode && (
            <>
              <Tooltip title={t('tracks.play')}>
                <IconButton
                  size="small"
                  color="primary"
                  onClick={() => audioApi.play({ track_id: track.id })}
                >
                  <PlayArrowIcon fontSize="small" />
                </IconButton>
              </Tooltip>
              {onEdit && (
                <Tooltip title={t('tracks.edit')}>
                  <IconButton size="small" onClick={() => onEdit(track)}>
                    <EditIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
              )}
              <Tooltip title={t('tracks.delete')}>
                <IconButton size="small" color="error" onClick={() => setTrackToDelete(track)}>
                  <DeleteIcon fontSize="small" />
                </IconButton>
              </Tooltip>
            </>
          )}
        </CardActions>
      </Card>
    </Box>
  );

  return (
    <Box sx={{ height: 'calc(100vh - 220px)', display: 'flex', flexDirection: 'column' }}>
      <Box display="flex" gap={2} mb={2} flexWrap="wrap" alignItems="center" flexShrink={0}>
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
        <TextField
          placeholder={t('track_selector.search_placeholder')}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          size="small"
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon />
              </InputAdornment>
            ),
          }}
          sx={{ minWidth: 200 }}
        />
        <ToggleButtonGroup
          value={filterSource}
          exclusive
          onChange={(_, v) => v && setFilterSource(v)}
          size="small"
        >
          <ToggleButton value="all">{t('tracks.filter.all')}</ToggleButton>
          <ToggleButton value="file">{t('tracks.filter.files')}</ToggleButton>
          <ToggleButton value="remote">{t('tracks.filter.remote', { defaultValue: 'Remote' })}</ToggleButton>
        </ToggleButtonGroup>

        {/* Sort controls */}
        <Box display="flex" alignItems="center" gap={0.5} ml="auto">
          <ToggleButtonGroup
            value={sortKey}
            exclusive
            onChange={handleSortKey}
            size="small"
          >
            <ToggleButton value="title">{t('tracks.fields.title')}</ToggleButton>
            <ToggleButton value="artist">{t('tracks.fields.artist')}</ToggleButton>
            <ToggleButton value="duration_ms">{t('tracks.fields.duration')}</ToggleButton>
            <ToggleButton value="last_played_at">{t('tracks.fields.last_played')}</ToggleButton>
          </ToggleButtonGroup>
          <Tooltip
            title={t(`tracks.sort.${sortDir}`)}
          >
            <IconButton
              size="small"
              onClick={() => setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))}
            >
              {sortDir === 'asc' ? (
                <ArrowUpwardIcon fontSize="small" />
              ) : (
                <ArrowDownwardIcon fontSize="small" />
              )}
            </IconButton>
          </Tooltip>
        </Box>
      </Box>

      <Box sx={{ flexGrow: 1, minHeight: 0 }}>
        {viewMode === 'card' ? (
          <VirtuosoGrid
            style={{ height: '100%' }}
            data={sorted}
            components={gridComponents as any}
            itemContent={renderGridItem}
          />
        ) : (
          <Virtuoso
            style={{ height: '100%' }}
            data={sorted}
            itemContent={renderListItem}
          />
        )}
      </Box>

      {/* Delete Confirmation */}
      <Dialog open={!!trackToDelete} onClose={() => setTrackToDelete(null)}>
        <DialogTitle sx={{ fontSize: '1.25rem', fontWeight: 600 }}>
          {t('tracks.delete')}
        </DialogTitle>
        <DialogContent>
          <DialogContentText>
            {t('tracks.delete_confirm', { title: trackToDelete?.title })}
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <ActionButton actionType="secondary" onClick={() => setTrackToDelete(null)}>
            {t('cancel', { ns: 'common' })}
          </ActionButton>
          <ActionButton
            actionType="destructive"
            onClick={() => {
              if (trackToDelete) {
                onDelete(trackToDelete);
                setTrackToDelete(null);
              }
            }}
          >
            {t('delete', { ns: 'common' })}
          </ActionButton>
        </DialogActions>
      </Dialog>
    </Box>
  );
};
