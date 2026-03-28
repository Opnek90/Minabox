import React, { useRef, useState } from 'react';
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
import ArrowDownwardIcon from '@mui/icons-material/ArrowDownward';
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward';
import AudiotrackIcon from '@mui/icons-material/Audiotrack';
import CreateNewFolderIcon from '@mui/icons-material/CreateNewFolder';
import DeleteIcon from '@mui/icons-material/Delete';
import DriveFileMoveIcon from '@mui/icons-material/DriveFileMove';
import EditIcon from '@mui/icons-material/Edit';
import FilterListIcon from '@mui/icons-material/FilterList';
import LinkIcon from '@mui/icons-material/Link';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import SearchIcon from '@mui/icons-material/Search';
import ViewListIcon from '@mui/icons-material/ViewList';
import ViewModuleIcon from '@mui/icons-material/ViewModule';
import { useTranslation } from 'react-i18next';
import { Virtuoso, VirtuosoGrid } from 'react-virtuoso';
import { audioApi } from '@/api/audio';
import type { Track, TrackFolder } from '@/types/api';
import { formatTime } from '@/utils/formatTime';
import { ActionButton } from '@/components/ui/ActionButton';
import { FolderBreadcrumb } from './FolderBreadcrumb';
import { FolderCreateDialog } from './FolderCreateDialog';
import { FolderList } from './FolderList';

type SortKey = 'title' | 'artist' | 'duration_ms' | 'last_played_at';
type FilterSource = 'all' | 'file' | 'remote';

const DEFAULT_FILTER: FilterSource = 'all';
const DEFAULT_SORT_KEY: SortKey = 'title';
const DEFAULT_SORT_DIR = 'asc' as const;

const LIST_ITEM_PR = '112px';

interface TrackListProps {
  tracks: Track[];
  allTracks: Track[];
  folders: TrackFolder[];
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
}

const gridComponents = {
  List: React.forwardRef<HTMLDivElement>((props, ref) => (
    <Grid container spacing={2} {...props} ref={ref} />
  )),
  Item: ({ children, ...props }: any) => (
    <Grid item xs={12} sm={6} md={4} {...props}>{children}</Grid>
  ),
};
gridComponents.List.displayName = 'GridList';

export const TrackList: React.FC<TrackListProps> = ({
  tracks,
  allTracks,
  folders,
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
}) => {
  const { t } = useTranslation('media');
  const theme = useTheme();
  const isDesktop = useMediaQuery(theme.breakpoints.up('md'));
  const filterBtnRef = useRef<HTMLButtonElement>(null);
  const [popoverOpen, setPopoverOpen] = useState(false);
  const [search, setSearch] = useState('');

  // Folder dialogs
  const [createFolderOpen, setCreateFolderOpen] = useState(false);
  const [renameFolder, setRenameFolder] = useState<TrackFolder | null>(null);
  const [moveTrack, setMoveTrack] = useState<Track | null>(null);

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

  // Only show tracks that belong to the current folder level
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

  // Move-to-folder: shows a simple list of available target folders
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
        {t('folders.move_to', { defaultValue: 'Move to folder' })}
      </Box>
      <Divider sx={{ mb: 0.5 }} />
      {currentFolderId !== null && (
        <Box
          component="button"
          onClick={() => { void onMoveTrackToFolder(moveTrack, null); setMoveTrack(null); }}
          sx={{ display: 'block', width: '100%', textAlign: 'left', background: 'none', border: 'none', cursor: 'pointer', px: 2, py: 0.75, borderRadius: 1, fontSize: '0.875rem', '&:hover': { bgcolor: 'action.hover' } }}
        >
          📁 {t('folders.root', { defaultValue: 'Library (root)' })}
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
    <ToggleButtonGroup
      value={typedFilter}
      exclusive
      onChange={(_, v) => v && onFilterChange(v)}
      size="small"
    >
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
      divider={index < sorted.length - 1}
      secondaryAction={
        !selectionMode && (
          <Box display="flex" alignItems="center">
            <Tooltip title={t('tracks.play')}>
              <IconButton size="small" color="primary" onClick={() => audioApi.play({ track_id: track.id })}>
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
            {folders.length > 0 && (
              <Tooltip title={t('folders.move_to', { defaultValue: 'Move to folder' })}>
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
          </Box>
        )
      }
      sx={{
        pr: selectionMode ? undefined : '148px',
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
            {track.last_played_at && (
              <Typography component="span" variant="caption" color="text.disabled" sx={{ flexShrink: 0 }}>
                ·{' '}
                {new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' }).format(
                  -Math.round((Date.now() - new Date(track.last_played_at).getTime()) / 3_600_000),
                  'hour'
                )}
              </Typography>
            )}
          </Box>
        }
      />
    </ListItem>
  );

  const renderGridItem = (_index: number, track: Track) => (
    <Box sx={{ p: 1, height: '100%' }}>
      <Card variant="outlined" sx={{ borderRadius: 2, height: '100%', display: 'flex', flexDirection: 'column' }}>
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
              {onEdit && (
                <Tooltip title={t('tracks.edit')}>
                  <IconButton size="small" onClick={() => onEdit(track)}>
                    <EditIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
              )}
              {folders.length > 0 && (
                <Tooltip title={t('folders.move_to', { defaultValue: 'Move to folder' })}>
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

  return (
    <Box sx={{ height: 'calc(100vh - 220px)', display: 'flex', flexDirection: 'column' }}>
      {/* Folder navigation */}
      <FolderBreadcrumb
        folders={folders}
        currentFolderId={currentFolderId}
        onNavigate={onNavigateFolder}
      />
      <FolderList
        folders={folders}
        currentFolderId={currentFolderId}
        allTracks={allTracks}
        onNavigate={onNavigateFolder}
        onRename={(folder) => setRenameFolder(folder)}
        onDelete={(folder) => void onFolderDelete(folder)}
      />

      {/* Toolbar */}
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

        <Tooltip title={t('folders.create_title', { defaultValue: 'New Folder' })}>
          <IconButton size="small" onClick={() => setCreateFolderOpen(true)} color="primary"
            sx={{ border: '1px solid', borderColor: 'primary.main', borderRadius: 1, px: 1 }}>
            <CreateNewFolderIcon fontSize="small" />
          </IconButton>
        </Tooltip>

        {isDesktop && <>{filterControls}{sortControls}</>}

        {!isDesktop && (
          <Tooltip title={t('tracks.filter.open')}>
            <IconButton
              ref={filterBtnRef}
              size="small"
              onClick={() => setPopoverOpen(true)}
              aria-label={t('tracks.filter.open')}
              sx={{
                overflow: 'visible',
                color: activeBadgeCount > 0 ? 'primary.main' : 'text.secondary',
                border: '1px solid',
                borderColor: activeBadgeCount > 0 ? 'primary.main' : 'divider',
                borderRadius: 1,
                px: 1,
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

      {/* Active Chips */}
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
          {hasActiveFilter && hasNonDefaultSort && (
            <Chip size="small" label={t('tracks.filter.reset_all')}
              onDelete={() => { onFilterChange(DEFAULT_FILTER); onSortChange(DEFAULT_SORT_KEY, DEFAULT_SORT_DIR); }}
              onClick={() => { onFilterChange(DEFAULT_FILTER); onSortChange(DEFAULT_SORT_KEY, DEFAULT_SORT_DIR); }}
              variant="outlined" sx={{ borderColor: 'divider', color: 'text.secondary' }} />
          )}
        </Box>
      )}

      {/* Mobile Popover */}
      <Popover
        open={popoverOpen && !isDesktop}
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
                sx={{ background: 'none', border: 'none', cursor: 'pointer', color: 'text.secondary', fontSize: '0.8rem', textAlign: 'left', p: 0, '&:hover': { color: 'text.primary' } }}>
                {t('tracks.filter.reset_all')}
              </Box>
            </>
          )}
        </Paper>
      </Popover>

      {/* List / Grid */}
      <Box sx={{ flexGrow: 1, minHeight: 0 }}>
        {tracksInCurrentFolder.length === 0 && folders.filter((f) => f.parent_id === currentFolderId).length === 0 ? (
          <Box display="flex" justifyContent="center" py={6}>
            <Typography color="text.secondary">{t('tracks.no_tracks')}</Typography>
          </Box>
        ) : viewMode === 'card' ? (
          <VirtuosoGrid style={{ height: '100%' }} data={sorted} components={gridComponents as any} itemContent={renderGridItem} />
        ) : (
          <Virtuoso style={{ height: '100%' }} data={sorted} itemContent={renderListItem} />
        )}
      </Box>

      {/* Folder Dialogs */}
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
    </Box>
  );
};
