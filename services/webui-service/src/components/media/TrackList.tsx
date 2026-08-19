import React, { useEffect, useRef, useState } from 'react';
import {
  Avatar,
  Box,
  Card,
  CardActions,
  CardContent,
  CardMedia,
  Chip,
  Divider,
  Grid,
  IconButton,
  InputAdornment,
  ListItem,
  ListItemAvatar,
  ListItemText,
  Menu,
  MenuItem,
  Paper,
  Popover,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Tooltip,
  Typography,
  useMediaQuery,
  useTheme,
} from '@mui/material';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import ArrowDownwardIcon from '@mui/icons-material/ArrowDownward';
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward';
import AudiotrackIcon from '@mui/icons-material/Audiotrack';
import DeleteIcon from '@mui/icons-material/Delete';
import DriveFileMoveIcon from '@mui/icons-material/DriveFileMove';
import EditIcon from '@mui/icons-material/Edit';
import FilterListIcon from '@mui/icons-material/FilterList';
import LinkIcon from '@mui/icons-material/Link';
import MoreVertIcon from '@mui/icons-material/MoreVert';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import PlaylistAddIcon from '@mui/icons-material/PlaylistAdd';
import SearchIcon from '@mui/icons-material/Search';
import ViewListIcon from '@mui/icons-material/ViewList';
import ViewModuleIcon from '@mui/icons-material/ViewModule';
import { useTranslation } from 'react-i18next';
import { Virtuoso, VirtuosoGrid } from 'react-virtuoso';
import { audioApi } from '@/api/audio';
import type { Playlist, Track, TrackFolder } from '@/types/api';
import { formatTime } from '@/utils/formatTime';
import { AddToPlaylistDialog } from './AddToPlaylistDialog';
import { FolderCreateDialog } from './FolderCreateDialog';
import { FolderTree } from './FolderTree';
import { useLayout } from '@/hooks/useLayout';

type SortKey = 'title' | 'artist' | 'duration_ms' | 'last_played_at';
type FilterSource = 'all' | 'file' | 'remote';

const DEFAULT_FILTER: FilterSource = 'all';
const DEFAULT_SORT_KEY: SortKey = 'title';
const DEFAULT_SORT_DIR = 'asc' as const;

const TREE_WIDTH = 220;

/** MIME type used for DnD transfer of a track ID */
const TRACK_DRAG_TYPE = 'application/minabox-track-id';

interface TrackListProps {
  tracks: Track[];
  allTracks: Track[];
  folders: TrackFolder[];
  playlists: Playlist[];
  currentFolderId: number | null;
  onNavigateFolder: (folderId: number | null) => void;
  onFolderCreate: (name: string, parentId: number | null) => Promise<void>;
  onFolderRename: (folder: TrackFolder, name: string) => Promise<void>;
  onFolderDelete: (folder: TrackFolder) => Promise<void>;
  onMoveTrackToFolder: (track: Track, folderId: number | null) => Promise<void>;
  onDelete: (track: Track) => void;
  onEdit?: (track: Track) => void;
  sortKey: string;
  sortDir: 'asc' | 'desc';
  onSortChange: (key: string, dir: 'asc' | 'desc') => void;
  viewMode: 'card' | 'list';
  onViewModeChange: (mode: 'card' | 'list') => void;
  filter: string;
  onFilterChange: (filter: string) => void;
  selectionMode?: boolean;
  onSelect?: (track: Track) => void;
  onRegisterCreateFolder?: (fn: () => void) => void;
  onPlaylistUpdated?: (playlist: Playlist) => void;
}

const gridComponents = {
  List: React.forwardRef<HTMLDivElement>((props, ref) => (
    <Grid container spacing={2} {...props} ref={ref} />
  )),
  Item: ({ children, ...props }: any) => (
    <Grid item xs={12} sm={6} lg={4} {...props}>{children}</Grid>
  ),
};
gridComponents.List.displayName = 'GridList';

export const TrackList: React.FC<TrackListProps> = ({
  tracks,
  allTracks,
  folders,
  playlists,
  currentFolderId,
  onNavigateFolder,
  onFolderCreate,
  onFolderRename,
  onFolderDelete,
  onMoveTrackToFolder,
  onDelete,
  onEdit,
  sortKey,
  sortDir,
  onSortChange,
  viewMode,
  onViewModeChange,
  filter,
  onFilterChange,
  selectionMode = false,
  onSelect,
  onRegisterCreateFolder,
  onPlaylistUpdated,
}) => {
  const { t } = useTranslation('media');
  const theme = useTheme();
  // Zwei Fragen, die vorher an derselben Grenze hingen und deshalb auf
  // Tablets beide falsch beantwortet wurden:
  // (1) Ist Platz fuer Sortierung, Filter und Zeilenaktionen in der Leiste?
  //     Ja ab Tablet – 834px reichen dafuer laengst.
  const hasInlineControls = useLayout().hasRoomForInlineControls;
  // (2) Passen Ordnerbaum und Trackliste nebeneinander? Der Baum belegt fix
  //     220px; darunter bliebe fuer die Liste zu wenig uebrig, also bleibt
  //     der Master-Detail-Wechsel bewusst bei 900px statt bei der Tablet-Kante.
  const hasSplitView = useMediaQuery(theme.breakpoints.up('md'));
  const filterBtnRef = useRef<HTMLButtonElement>(null);
  const [popoverOpen, setPopoverOpen] = useState(false);
  const [search, setSearch] = useState('');

  const [createFolderOpen, setCreateFolderOpen] = useState(false);
  const [renameFolder, setRenameFolder] = useState<TrackFolder | null>(null);
  const [moveTrack, setMoveTrack] = useState<Track | null>(null);

  const [menuAnchor, setMenuAnchor] = useState<HTMLElement | null>(null);
  const [menuTrack, setMenuTrack] = useState<Track | null>(null);

  const [addToPlaylistTrack, setAddToPlaylistTrack] = useState<Track | null>(null);

  const [mobileView, setMobileView] = useState<'tree' | 'tracks'>(
    currentFolderId === null ? 'tree' : 'tracks'
  );

  /** Track that is currently being dragged (set on dragstart, cleared on dragend) */
  const [draggingTrackId, setDraggingTrackId] = useState<number | null>(null);

  useEffect(() => {
    onRegisterCreateFolder?.(() => setCreateFolderOpen(true));
  }, [onRegisterCreateFolder]);

  const typedSortKey = sortKey as SortKey;
  const typedFilter = filter as FilterSource;

  const hasActiveFilter = typedFilter !== DEFAULT_FILTER;
  const hasNonDefaultSort = typedSortKey !== DEFAULT_SORT_KEY || sortDir !== DEFAULT_SORT_DIR;
  const hasAnyActiveChip = hasActiveFilter || hasNonDefaultSort;
  const activeBadgeCount = (hasActiveFilter ? 1 : 0) + (hasNonDefaultSort ? 1 : 0);

  const filterLabel: Record<FilterSource, string> = {
    all: t('tracks.filter.all'),
    file: t('tracks.filter.files'),
    remote: t('tracks.filter.remote'),
  };
  const sortKeyLabel: Record<SortKey, string> = {
    title: t('tracks.fields.title'),
    artist: t('tracks.fields.artist'),
    duration_ms: t('tracks.fields.duration'),
    last_played_at: t('tracks.fields.last_played'),
  };

  const tracksInCurrentFolder = tracks.filter((tr) =>
    currentFolderId === null ? tr.folder_id == null : tr.folder_id === currentFolderId
  );

  const filtered = tracksInCurrentFolder.filter((tr) => {
    const q = search.toLowerCase();
    const matchesSearch =
      tr.title.toLowerCase().includes(q) ||
      (tr.artist ?? '').toLowerCase().includes(q) ||
      (tr.album ?? '').toLowerCase().includes(q);
    const matchesFilter = typedFilter === 'all' || tr.source_type === typedFilter;
    return matchesSearch && matchesFilter;
  });

  const sorted = [...filtered].sort((a, b) => {
    let aVal: string | number;
    let bVal: string | number;
    if (typedSortKey === 'duration_ms') {
      aVal = a.duration_ms ?? 0; bVal = b.duration_ms ?? 0;
    } else if (typedSortKey === 'last_played_at') {
      aVal = a.last_played_at ? new Date(a.last_played_at).getTime() : 0;
      bVal = b.last_played_at ? new Date(b.last_played_at).getTime() : 0;
    } else if (typedSortKey === 'artist') {
      aVal = (a.artist ?? '').toLowerCase(); bVal = (b.artist ?? '').toLowerCase();
    } else {
      aVal = a.title.toLowerCase(); bVal = b.title.toLowerCase();
    }
    if (aVal < bVal) return sortDir === 'asc' ? -1 : 1;
    if (aVal > bVal) return sortDir === 'asc' ? 1 : -1;
    return 0;
  });

  const handleSortKey = (_: React.MouseEvent, key: SortKey | null) => {
    if (!key) return;
    if (key === typedSortKey) onSortChange(key, sortDir === 'asc' ? 'desc' : 'asc');
    else onSortChange(key, 'asc');
  };

  const handleSortDirToggle = () =>
    onSortChange(typedSortKey, sortDir === 'asc' ? 'desc' : 'asc');

  const handleNavigateFolder = (folderId: number | null) => {
    onNavigateFolder(folderId);
    if (!hasSplitView) setMobileView('tracks');
  };

  const handleMenuOpen = (event: React.MouseEvent<HTMLElement>, track: Track) => {
    event.stopPropagation();
    setMenuAnchor(event.currentTarget);
    setMenuTrack(track);
  };

  const handleMenuClose = () => {
    setMenuAnchor(null);
    setMenuTrack(null);
  };

  // --- Drag & Drop helpers ---
  const handleDragStart = (e: React.DragEvent, track: Track) => {
    e.dataTransfer.setData(TRACK_DRAG_TYPE, String(track.id));
    e.dataTransfer.effectAllowed = 'move';
    setDraggingTrackId(track.id);
  };

  const handleDragEnd = () => setDraggingTrackId(null);

  /**
   * Called by FolderTree when a track is dropped onto a folder node.
   * Looks up the full Track object and delegates to onMoveTrackToFolder.
   */
  const handleDropTrackOnFolder = (trackId: number, targetFolderId: number | null) => {
    const track = allTracks.find((tr) => tr.id === trackId);
    if (track) {
      void onMoveTrackToFolder(track, targetFolderId);
    }
  };

  const MoveMenu = moveTrack ? (
    <Popover
      open
      onClose={() => setMoveTrack(null)}
      anchorReference="anchorPosition"
      anchorPosition={{ top: window.innerHeight / 2, left: window.innerWidth / 2 }}
      transformOrigin={{ vertical: 'center', horizontal: 'center' }}
      slotProps={{ paper: { sx: { minWidth: 220, borderRadius: 2, p: 1 } } }}
    >
      <Box sx={{ fontWeight: 600, px: 1, pb: 0.5, fontSize: '0.85rem', color: 'text.secondary' }}>
        {t('folders.move_to')}
      </Box>
      <Divider sx={{ mb: 0.5 }} />
      {currentFolderId !== null && (
        <Box
          component="button"
          onClick={() => { void onMoveTrackToFolder(moveTrack, null); setMoveTrack(null); }}
          sx={{ display: 'block', width: '100%', textAlign: 'left', background: 'none', border: 'none', cursor: 'pointer', px: 2, py: 0.75, borderRadius: 1, fontSize: '0.875rem', '&:hover': { bgcolor: 'action.hover' } }}
        >
          📁 {t('folders.root')}
        </Box>
      )}
      {folders.map((f) => f.id !== currentFolderId && (
        <Box
          key={f.id}
          component="button"
          onClick={() => { void onMoveTrackToFolder(moveTrack, f.id); setMoveTrack(null); }}
          sx={{ display: 'block', width: '100%', textAlign: 'left', background: 'none', border: 'none', cursor: 'pointer', px: 2, py: 0.75, borderRadius: 1, fontSize: '0.875rem', '&:hover': { bgcolor: 'action.hover' } }}
        >
          📂 {f.name}
        </Box>
      ))}
    </Popover>
  ) : null;

  const filterControls = (
    <ToggleButtonGroup value={typedFilter} exclusive onChange={(_, v) => v && onFilterChange(v)} size="small">
      <ToggleButton value="all">{t('tracks.filter.all')}</ToggleButton>
      <ToggleButton value="file">{t('tracks.filter.files')}</ToggleButton>
      <ToggleButton value="remote">{t('tracks.filter.remote')}</ToggleButton>
    </ToggleButtonGroup>
  );

  const sortControls = (
    <Box display="flex" alignItems="center" gap={0.5}>
      <ToggleButtonGroup value={typedSortKey} exclusive onChange={handleSortKey} size="small">
        <ToggleButton value="title">{t('tracks.fields.title')}</ToggleButton>
        <ToggleButton value="artist">{t('tracks.fields.artist')}</ToggleButton>
        <ToggleButton value="duration_ms">{t('tracks.fields.duration')}</ToggleButton>
        <ToggleButton value="last_played_at">{t('tracks.fields.last_played')}</ToggleButton>
      </ToggleButtonGroup>
      <Tooltip title={sortDir === 'asc' ? t('tracks.sort.asc') : t('tracks.sort.desc')}>
        <IconButton size="small" onClick={handleSortDirToggle}>
          {sortDir === 'asc' ? <ArrowUpwardIcon fontSize="small" /> : <ArrowDownwardIcon fontSize="small" />}
        </IconButton>
      </Tooltip>
    </Box>
  );

  const renderListItem = (index: number, track: Track) => (
    <ListItem
      key={track.id}
      draggable={!selectionMode}
      onDragStart={!selectionMode ? (e) => handleDragStart(e, track) : undefined}
      onDragEnd={!selectionMode ? handleDragEnd : undefined}
      divider={index < sorted.length - 1}
      secondaryAction={
        !selectionMode && (
          <Box display="flex" alignItems="center">
            {hasInlineControls && (
              <>
                <Tooltip title={t('tracks.play')}>
                  <IconButton size="small" color="primary" onClick={() => audioApi.play({ track_id: track.id })}>
                    <PlayArrowIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
                {playlists.length > 0 && (
                  <Tooltip title={t('playlists.add_to_playlist')}>
                    <IconButton size="small" onClick={() => setAddToPlaylistTrack(track)}>
                      <PlaylistAddIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                )}
                {onEdit && (
                  <Tooltip title={t('tracks.edit')}>
                    <IconButton size="small" onClick={() => onEdit(track)}>
                      <EditIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                )}
                {folders.length > 0 && (
                  <Tooltip title={t('folders.move_to')}>
                    <IconButton size="small" onClick={() => setMoveTrack(track)}>
                      <DriveFileMoveIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                )}
                <Tooltip title={t('tracks.delete')}>
                  <IconButton size="small" color="error" onClick={() => onDelete(track)}>
                    <DeleteIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
              </>
            )}
            {!hasInlineControls && (
              <IconButton size="small" onClick={(e) => handleMenuOpen(e, track)}>
                <MoreVertIcon fontSize="small" />
              </IconButton>
            )}
          </Box>
        )
      }
      sx={{
        pr: selectionMode ? undefined : hasInlineControls ? '180px' : '40px',
        opacity: draggingTrackId === track.id ? 0.4 : 1,
        cursor: selectionMode ? 'default' : 'grab',
        transition: 'opacity 0.15s',
        ...(selectionMode ? { cursor: 'pointer', '&:hover': { bgcolor: 'action.hover' } } : {}),
      }}
      onClick={selectionMode && onSelect ? () => onSelect(track) : undefined}
    >
      <ListItemAvatar sx={{ minWidth: 44 }}>
        {track.cover_art_url ? (
          <Avatar src={track.cover_art_url} variant="rounded" sx={{ width: 40, height: 40 }}>
            <AudiotrackIcon />
          </Avatar>
        ) : (
          <Avatar variant="rounded" sx={{ width: 40, height: 40, bgcolor: 'action.selected' }}>
            {track.source_type === 'remote' ? <LinkIcon fontSize="small" /> : <AudiotrackIcon fontSize="small" />}
          </Avatar>
        )}
      </ListItemAvatar>
      <ListItemText
        primary={track.title}
        primaryTypographyProps={{ noWrap: true }}
        secondary={
          <Box component="span" display="flex" gap={1} alignItems="center" flexWrap="wrap">
            {track.artist && <Typography component="span" variant="caption" noWrap>{track.artist}</Typography>}
            {track.album && <Typography component="span" variant="caption" color="text.disabled" noWrap>· {track.album}</Typography>}
            {track.duration_ms != null && (
              <Chip label={formatTime(track.duration_ms)} size="small" variant="outlined"
                sx={{ height: 18, fontSize: '0.65rem', flexShrink: 0 }} />
            )}
          </Box>
        }
      />
    </ListItem>
  );

  const renderGridItem = (_index: number, track: Track) => (
    <Box
      sx={{ p: 1, height: '100%' }}
      draggable={!selectionMode}
      onDragStart={!selectionMode ? (e) => handleDragStart(e, track) : undefined}
      onDragEnd={!selectionMode ? handleDragEnd : undefined}
    >
      <Card
        variant="outlined"
        sx={{
          borderRadius: 2,
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          opacity: draggingTrackId === track.id ? 0.4 : 1,
          cursor: selectionMode ? 'default' : 'grab',
          transition: 'opacity 0.15s',
        }}
      >
        {track.cover_art_url && (
          <CardMedia component="img" height="120" image={track.cover_art_url} alt={track.title} sx={{ objectFit: 'cover' }} />
        )}
        <CardContent sx={{ pb: 0, flex: 1 }}>
          <Typography variant="subtitle1" fontWeight={600} display="flex" alignItems="center" gap={1}>
            {track.source_type === 'remote'
              ? <LinkIcon fontSize="small" color="primary" />
              : <AudiotrackIcon fontSize="small" color="primary" />}
            {track.title}
          </Typography>
          {(track.artist || track.album) && (
            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }} noWrap>
              {[track.artist, track.album].filter(Boolean).join(' · ')}
            </Typography>
          )}
          {track.duration_ms != null && (
            <Chip label={formatTime(track.duration_ms)} size="small" variant="outlined" sx={{ mt: 1 }} />
          )}
        </CardContent>
        <CardActions sx={{ pt: 0 }}>
          {!selectionMode && (
            <>
              <Tooltip title={t('tracks.play')}>
                <IconButton size="small" color="primary" onClick={() => audioApi.play({ track_id: track.id })}>
                  <PlayArrowIcon fontSize="small" />
                </IconButton>
              </Tooltip>
              {playlists.length > 0 && (
                <Tooltip title={t('playlists.add_to_playlist')}>
                  <IconButton size="small" onClick={() => setAddToPlaylistTrack(track)}>
                    <PlaylistAddIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
              )}
              {onEdit && (
                <Tooltip title={t('tracks.edit')}>
                  <IconButton size="small" onClick={() => onEdit(track)}>
                    <EditIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
              )}
              {folders.length > 0 && (
                <Tooltip title={t('folders.move_to')}>
                  <IconButton size="small" onClick={() => setMoveTrack(track)}>
                    <DriveFileMoveIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
              )}
              <Tooltip title={t('tracks.delete')}>
                <IconButton size="small" color="error" onClick={() => onDelete(track)}>
                  <DeleteIcon fontSize="small" />
                </IconButton>
              </Tooltip>
            </>
          )}
        </CardActions>
      </Card>
    </Box>
  );

  const mobileActionsMenu = (
    <Menu
      anchorEl={menuAnchor}
      open={Boolean(menuAnchor) && menuTrack !== null}
      onClose={handleMenuClose}
      transformOrigin={{ horizontal: 'right', vertical: 'top' }}
      anchorOrigin={{ horizontal: 'right', vertical: 'bottom' }}
    >
      <MenuItem onClick={() => { if (menuTrack) audioApi.play({ track_id: menuTrack.id }); handleMenuClose(); }}>
        <PlayArrowIcon fontSize="small" sx={{ mr: 1.5, color: 'primary.main' }} />
        {t('tracks.play')}
      </MenuItem>
      {playlists.length > 0 && (
        <MenuItem onClick={() => { if (menuTrack) setAddToPlaylistTrack(menuTrack); handleMenuClose(); }}>
          <PlaylistAddIcon fontSize="small" sx={{ mr: 1.5 }} />
          {t('playlists.add_to_playlist')}
        </MenuItem>
      )}
      {onEdit && (
        <MenuItem onClick={() => { if (menuTrack) onEdit(menuTrack); handleMenuClose(); }}>
          <EditIcon fontSize="small" sx={{ mr: 1.5 }} />
          {t('tracks.edit')}
        </MenuItem>
      )}
      {folders.length > 0 && (
        <MenuItem onClick={() => { if (menuTrack) setMoveTrack(menuTrack); handleMenuClose(); }}>
          <DriveFileMoveIcon fontSize="small" sx={{ mr: 1.5 }} />
          {t('folders.move_to')}
        </MenuItem>
      )}
      <Divider />
      <MenuItem
        onClick={() => { if (menuTrack) onDelete(menuTrack); handleMenuClose(); }}
        sx={{ color: 'error.main' }}
      >
        <DeleteIcon fontSize="small" sx={{ mr: 1.5 }} />
        {t('tracks.delete')}
      </MenuItem>
    </Menu>
  );

  const trackPanel = (
    <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column', minWidth: 0 }}>
      {!hasSplitView && (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
          <IconButton size="small" onClick={() => setMobileView('tree')}>
            <ArrowBackIcon fontSize="small" />
          </IconButton>
          <Typography variant="body2" fontWeight={600} noWrap>
            {currentFolderId === null
              ? t('folders.root')
              : folders.find((f) => f.id === currentFolderId)?.name ?? ''}
          </Typography>
        </Box>
      )}

      <Box display="flex" gap={1} mb={1} alignItems="center" flexWrap="wrap" flexShrink={0}>
        <ToggleButtonGroup value={viewMode} exclusive onChange={(_, v) => v && onViewModeChange(v)} size="small">
          <ToggleButton value="card" aria-label={t('view_mode_card')}><ViewModuleIcon fontSize="small" /></ToggleButton>
          <ToggleButton value="list" aria-label={t('view_mode_list')}><ViewListIcon fontSize="small" /></ToggleButton>
        </ToggleButtonGroup>

        <TextField
          placeholder={t('track_selector.search_placeholder')}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          size="small"
          InputProps={{ startAdornment: <InputAdornment position="start"><SearchIcon fontSize="small" /></InputAdornment> }}
          sx={{ flex: 1, minWidth: 0 }}
        />

        {hasInlineControls && <>{filterControls}{sortControls}</>}

        {!hasInlineControls && (
          <Tooltip title={t('tracks.filter.open')}>
            <IconButton
              ref={filterBtnRef}
              size="small"
              onClick={() => setPopoverOpen(true)}
              sx={{
                overflow: 'visible',
                color: activeBadgeCount > 0 ? 'primary.main' : 'text.secondary',
                border: '1px solid',
                borderColor: activeBadgeCount > 0 ? 'primary.main' : 'divider',
                borderRadius: 1, px: 1,
              }}
            >
              <FilterListIcon fontSize="small" />
              {activeBadgeCount > 0 && (
                <Box component="span" sx={{
                  position: 'absolute', top: -6, right: -6,
                  width: 16, height: 16, borderRadius: '50%',
                  bgcolor: 'primary.main', color: 'primary.contrastText',
                  fontSize: '0.65rem', fontWeight: 700,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  pointerEvents: 'none',
                }}>
                  {activeBadgeCount}
                </Box>
              )}
            </IconButton>
          </Tooltip>
        )}
      </Box>

      {hasAnyActiveChip && (
        <Box display="flex" gap={0.75} flexWrap="wrap" mb={1} alignItems="center" flexShrink={0}>
          {hasActiveFilter && (
            <Chip size="small" label={filterLabel[typedFilter]}
              onDelete={() => onFilterChange(DEFAULT_FILTER)} color="primary" variant="outlined" />
          )}
          {hasNonDefaultSort && (
            <Chip size="small"
              icon={sortDir === 'asc' ? <ArrowUpwardIcon /> : <ArrowDownwardIcon />}
              label={sortKeyLabel[typedSortKey]}
              onDelete={() => onSortChange(DEFAULT_SORT_KEY, DEFAULT_SORT_DIR)}
              color="primary" variant="outlined" />
          )}
        </Box>
      )}

      <Popover
        open={popoverOpen && !hasInlineControls}
        anchorEl={filterBtnRef.current}
        onClose={() => setPopoverOpen(false)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        transformOrigin={{ vertical: 'top', horizontal: 'right' }}
        slotProps={{ paper: { sx: { mt: 0.5, borderRadius: 2, minWidth: 300 } } }}
      >
        <Paper sx={{ p: 2, display: 'flex', flexDirection: 'column', gap: 2 }}>
          <Box>
            <Typography variant="caption" color="text.secondary" fontWeight={600} display="block" mb={0.75}>
              {t('tracks.filter.label')}
            </Typography>
            <ToggleButtonGroup value={typedFilter} exclusive onChange={(_, v) => v && onFilterChange(v)}
              size="small" fullWidth sx={{ '& .MuiToggleButton-root': { flex: 1, fontSize: '0.78rem' } }}>
              <ToggleButton value="all">{t('tracks.filter.all')}</ToggleButton>
              <ToggleButton value="file">{t('tracks.filter.files')}</ToggleButton>
              <ToggleButton value="remote">{t('tracks.filter.remote')}</ToggleButton>
            </ToggleButtonGroup>
          </Box>
          <Divider />
          <Box>
            <Typography variant="caption" color="text.secondary" fontWeight={600} display="block" mb={0.75}>
              {t('tracks.sort.label')}
            </Typography>
            <Box display="flex" gap={1} alignItems="center">
              <ToggleButtonGroup value={typedSortKey} exclusive onChange={handleSortKey}
                size="small" sx={{ flex: 1, '& .MuiToggleButton-root': { flex: 1, fontSize: '0.7rem' } }}>
                <ToggleButton value="title">{t('tracks.fields.title')}</ToggleButton>
                <ToggleButton value="artist">{t('tracks.fields.artist')}</ToggleButton>
                <ToggleButton value="duration_ms">{t('tracks.fields.duration')}</ToggleButton>
                <ToggleButton value="last_played_at">{t('tracks.fields.last_played')}</ToggleButton>
              </ToggleButtonGroup>
              <Tooltip title={sortDir === 'asc' ? t('tracks.sort.asc') : t('tracks.sort.desc')}>
                <IconButton size="small" onClick={handleSortDirToggle}>
                  {sortDir === 'asc' ? <ArrowUpwardIcon fontSize="small" /> : <ArrowDownwardIcon fontSize="small" />}
                </IconButton>
              </Tooltip>
            </Box>
          </Box>
          {hasAnyActiveChip && (
            <>
              <Divider />
              <Box component="button"
                onClick={() => { onFilterChange(DEFAULT_FILTER); onSortChange(DEFAULT_SORT_KEY, DEFAULT_SORT_DIR); setPopoverOpen(false); }}
                sx={{ background: 'none', border: 'none', cursor: 'pointer', color: 'text.secondary', fontSize: '0.8rem', textAlign: 'left', p: 0 }}>
                {t('tracks.filter.reset_all')}
              </Box>
            </>
          )}
        </Paper>
      </Popover>

      <Box sx={{ flexGrow: 1, minHeight: 0 }}>
        {sorted.length === 0 ? (
          <Box display="flex" justifyContent="center" py={6}>
            <Typography color="text.secondary">{t('tracks.no_tracks')}</Typography>
          </Box>
        ) : viewMode === 'card' ? (
          <VirtuosoGrid style={{ height: '100%' }} data={sorted} components={gridComponents as any} itemContent={renderGridItem} />
        ) : (
          <Virtuoso style={{ height: '100%' }} data={sorted} itemContent={renderListItem} />
        )}
      </Box>
    </Box>
  );

  return (
    <Box
      sx={{
        // dvh: gegen die *kleinste* Viewport-Hoehe rechnen, sonst ragt der
        // Panel auf Mobil unter die eingeblendete URL-Leiste und die innere
        // Virtuoso-Liste bekommt einen zweiten, konkurrierenden Scroll.
        height: 'calc(100vh - 220px)',
        '@supports (height: 100dvh)': { height: 'calc(100dvh - 220px)' },
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {hasSplitView ? (
        <Box sx={{ display: 'flex', flex: 1, minHeight: 0, gap: 0 }}>
          <Box sx={{ width: TREE_WIDTH, flexShrink: 0, height: '100%' }}>
            <FolderTree
              folders={folders}
              allTracks={allTracks}
              currentFolderId={currentFolderId}
              onNavigate={handleNavigateFolder}
              onRename={(folder) => setRenameFolder(folder)}
              onDelete={(folder) => void onFolderDelete(folder)}
              onDropTrack={handleDropTrackOnFolder}
            />
          </Box>
          <Box sx={{ flex: 1, minWidth: 0, pl: 2, height: '100%', display: 'flex', flexDirection: 'column' }}>
            {trackPanel}
          </Box>
        </Box>
      ) : (
        <Box sx={{ flex: 1, minHeight: 0 }}>
          {mobileView === 'tree' ? (
            <FolderTree
              folders={folders}
              allTracks={allTracks}
              currentFolderId={currentFolderId}
              onNavigate={handleNavigateFolder}
              onRename={(folder) => setRenameFolder(folder)}
              onDelete={(folder) => void onFolderDelete(folder)}
              onDropTrack={handleDropTrackOnFolder}
            />
          ) : (
            trackPanel
          )}
        </Box>
      )}

      <FolderCreateDialog
        open={createFolderOpen}
        onClose={() => setCreateFolderOpen(false)}
        onSubmit={(name) => onFolderCreate(name, currentFolderId)}
      />
      <FolderCreateDialog
        open={!!renameFolder}
        initialName={renameFolder?.name}
        onClose={() => setRenameFolder(null)}
        onSubmit={(name) => onFolderRename(renameFolder!, name)}
      />

      {MoveMenu}
      {mobileActionsMenu}

      <AddToPlaylistDialog
        open={!!addToPlaylistTrack}
        track={addToPlaylistTrack}
        playlists={playlists}
        onClose={() => setAddToPlaylistTrack(null)}
        onAdded={(pl) => onPlaylistUpdated?.(pl)}
      />
    </Box>
  );
};
