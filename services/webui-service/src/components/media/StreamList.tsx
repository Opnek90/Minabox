import React, { useEffect, useRef, useState } from 'react';
import {
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
  List,
  ListItem,
  ListItemText,
  Menu,
  MenuItem,
  Pagination,
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
import ChevronLeftIcon from '@mui/icons-material/ChevronLeft';
import ChevronRightIcon from '@mui/icons-material/ChevronRight';
import DeleteIcon from '@mui/icons-material/Delete';
import DriveFileMoveIcon from '@mui/icons-material/DriveFileMove';
import EditIcon from '@mui/icons-material/Edit';
import FilterListIcon from '@mui/icons-material/FilterList';
import MoreVertIcon from '@mui/icons-material/MoreVert';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import SearchIcon from '@mui/icons-material/Search';
import StreamIcon from '@mui/icons-material/Stream';
import ViewListIcon from '@mui/icons-material/ViewList';
import ViewModuleIcon from '@mui/icons-material/ViewModule';
import { useTranslation } from 'react-i18next';
import { audioApi } from '@/api/audio';
import { LastPlayedCaption } from '@/components/media/LastPlayedCaption';
import { StreamEditDialog } from '@/components/media/StreamEditDialog';
import { FolderCreateDialog } from './FolderCreateDialog';
import { FolderTree } from './FolderTree';
import type { Stream, StreamFolder } from '@/types/api';
import { useLayout } from '@/hooks/useLayout';

type SortKey = 'title' | 'artist' | 'last_played_at';

const DEFAULT_SORT_KEY: SortKey = 'title';
const DEFAULT_SORT_DIR = 'asc' as const;

const TREE_WIDTH = 220;
const TREE_COLLAPSED_WIDTH = 36;
const PAGE_SIZE_OPTIONS = [25, 50] as const;
const DEFAULT_PAGE_SIZE = 25;

/** MIME type used for DnD transfer of a stream ID */
const STREAM_DRAG_TYPE = 'application/minabox-stream-id';

// Desktop: 4 Buttons (Play + Edit + Move + Delete) à ~32px = ~136px
const LIST_ITEM_PR_DESKTOP = '136px';
// Mobile: single MoreVert button
const LIST_ITEM_PR_MOBILE = '40px';

interface StreamListProps {
  streams: Stream[];
  allStreams: Stream[];
  folders: StreamFolder[];
  currentFolderId: number | null;
  onNavigateFolder: (folderId: number | null) => void;
  onFolderCreate: (name: string, parentId: number | null) => Promise<void>;
  onFolderRename: (folder: StreamFolder, name: string) => Promise<void>;
  onFolderDelete: (folder: StreamFolder) => Promise<void>;
  onMoveStreamToFolder: (stream: Stream, folderId: number | null) => Promise<void>;
  onDelete: (stream: Stream) => void;
  onUpdate: (stream: Stream) => void;
  sortKey: string;
  sortDir: 'asc' | 'desc';
  onSortChange: (key: string, dir: 'asc' | 'desc') => void;
  viewMode: 'card' | 'list';
  onViewModeChange: (mode: 'card' | 'list') => void;
  treeCollapsed?: boolean;
  onTreeCollapsedChange?: (collapsed: boolean) => void;
  pageSize?: number;
  onPageSizeChange?: (size: number) => void;
  onRegisterCreateFolder?: (fn: () => void) => void;
}

export const StreamList: React.FC<StreamListProps> = ({
  streams,
  allStreams,
  folders,
  currentFolderId,
  onNavigateFolder,
  onFolderCreate,
  onFolderRename,
  onFolderDelete,
  onMoveStreamToFolder,
  onDelete,
  onUpdate,
  sortKey,
  sortDir,
  onSortChange,
  viewMode,
  onViewModeChange,
  treeCollapsed = false,
  onTreeCollapsedChange,
  pageSize = DEFAULT_PAGE_SIZE,
  onPageSizeChange,
  onRegisterCreateFolder,
}) => {
  const { t } = useTranslation('media');
  const theme = useTheme();
  const hasInlineControls = useLayout().hasRoomForInlineControls;
  const hasSplitView = useMediaQuery(theme.breakpoints.up('md'));
  const filterBtnRef = useRef<HTMLButtonElement>(null);
  const [popoverOpen, setPopoverOpen] = useState(false);
  const [search, setSearch] = useState('');
  const [streamToEdit, setStreamToEdit] = useState<Stream | null>(null);

  const [createFolderOpen, setCreateFolderOpen] = useState(false);
  const [renameFolder, setRenameFolder] = useState<StreamFolder | null>(null);
  const [moveStream, setMoveStream] = useState<Stream | null>(null);

  const [menuAnchor, setMenuAnchor] = useState<HTMLElement | null>(null);
  const [menuStream, setMenuStream] = useState<Stream | null>(null);

  const [mobileView, setMobileView] = useState<'tree' | 'list'>(
    currentFolderId === null ? 'tree' : 'list'
  );

  const [draggingStreamId, setDraggingStreamId] = useState<number | null>(null);
  const [page, setPage] = useState(1);

  useEffect(() => {
    onRegisterCreateFolder?.(() => setCreateFolderOpen(true));
  }, [onRegisterCreateFolder]);

  const typedSortKey = sortKey as SortKey;
  const hasNonDefaultSort = typedSortKey !== DEFAULT_SORT_KEY || sortDir !== DEFAULT_SORT_DIR;

  const sortKeyLabel: Record<SortKey, string> = {
    title: t('streams.fields.title'),
    artist: t('streams.fields.artist'),
    last_played_at: t('streams.fields.last_played'),
  };

  const streamsInCurrentFolder = streams.filter((s) =>
    currentFolderId === null ? s.folder_id == null : s.folder_id === currentFolderId
  );

  const filtered = streamsInCurrentFolder.filter((s) => {
    const q = search.toLowerCase();
    return s.title.toLowerCase().includes(q) || (s.artist ?? '').toLowerCase().includes(q);
  });

  const sorted = [...filtered].sort((a, b) => {
    let aVal: string | number;
    let bVal: string | number;
    if (typedSortKey === 'last_played_at') {
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

  const totalPages = Math.max(1, Math.ceil(sorted.length / pageSize));
  const currentPage = Math.min(page, totalPages);
  const paginated = sorted.slice((currentPage - 1) * pageSize, currentPage * pageSize);

  useEffect(() => {
    setPage(1);
  }, [search, typedSortKey, sortDir, currentFolderId, pageSize]);

  const handlePageSizeChange = (size: number) => {
    onPageSizeChange?.(size);
  };

  const handleSortKey = (_: React.MouseEvent, key: SortKey | null) => {
    if (!key) return;
    if (key === typedSortKey) onSortChange(key, sortDir === 'asc' ? 'desc' : 'asc');
    else onSortChange(key, 'asc');
  };

  const handleSortDirToggle = () =>
    onSortChange(typedSortKey, sortDir === 'asc' ? 'desc' : 'asc');

  const handleNavigateFolder = (folderId: number | null) => {
    onNavigateFolder(folderId);
    if (!hasSplitView) setMobileView('list');
  };

  const handleMenuOpen = (e: React.MouseEvent<HTMLElement>, stream: Stream) => {
    e.stopPropagation();
    setMenuAnchor(e.currentTarget);
    setMenuStream(stream);
  };

  const handleMenuClose = () => {
    setMenuAnchor(null);
    setMenuStream(null);
  };

  // --- Drag & Drop helpers ---
  const handleDragStart = (e: React.DragEvent, stream: Stream) => {
    e.dataTransfer.setData(STREAM_DRAG_TYPE, String(stream.id));
    e.dataTransfer.effectAllowed = 'move';
    setDraggingStreamId(stream.id);
  };

  const handleDragEnd = () => setDraggingStreamId(null);

  const handleDropStreamOnFolder = (streamId: number, targetFolderId: number | null) => {
    const stream = allStreams.find((s) => s.id === streamId);
    if (stream) {
      void onMoveStreamToFolder(stream, targetFolderId);
    }
  };

  const MoveMenu = moveStream ? (
    <Popover
      open
      onClose={() => setMoveStream(null)}
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
          onClick={() => { void onMoveStreamToFolder(moveStream, null); setMoveStream(null); }}
          sx={{ display: 'block', width: '100%', textAlign: 'left', background: 'none', border: 'none', cursor: 'pointer', px: 2, py: 0.75, borderRadius: 1, fontSize: '0.875rem', '&:hover': { bgcolor: 'action.hover' } }}
        >
          📁 {t('folders.root')}
        </Box>
      )}
      {folders.map((f) => f.id !== currentFolderId && (
        <Box
          key={f.id}
          component="button"
          onClick={() => { void onMoveStreamToFolder(moveStream, f.id); setMoveStream(null); }}
          sx={{ display: 'block', width: '100%', textAlign: 'left', background: 'none', border: 'none', cursor: 'pointer', px: 2, py: 0.75, borderRadius: 1, fontSize: '0.875rem', '&:hover': { bgcolor: 'action.hover' } }}
        >
          📂 {f.name}
        </Box>
      ))}
    </Popover>
  ) : null;

  const sortControls = (
    <Box display="flex" alignItems="center" gap={0.5}>
      <ToggleButtonGroup value={typedSortKey} exclusive onChange={handleSortKey} size="small">
        <ToggleButton value="title">{t('streams.fields.title')}</ToggleButton>
        <ToggleButton value="artist">{t('streams.fields.artist')}</ToggleButton>
        <ToggleButton value="last_played_at">{t('streams.fields.last_played')}</ToggleButton>
      </ToggleButtonGroup>
      <Tooltip title={sortDir === 'asc' ? t('streams.sort.asc') : t('streams.sort.desc')}>
        <IconButton size="small" onClick={handleSortDirToggle}>
          {sortDir === 'asc' ? <ArrowUpwardIcon fontSize="small" /> : <ArrowDownwardIcon fontSize="small" />}
        </IconButton>
      </Tooltip>
    </Box>
  );

  const desktopActions = (stream: Stream) => (
    <>
      <Tooltip title={t('tracks.play')}>
        <IconButton size="small" color="primary" onClick={() => audioApi.play({ stream_id: stream.id })}>
          <PlayArrowIcon fontSize="small" />
        </IconButton>
      </Tooltip>
      <Tooltip title={t('streams.edit')}>
        <IconButton size="small" onClick={() => setStreamToEdit(stream)}>
          <EditIcon fontSize="small" />
        </IconButton>
      </Tooltip>
      {folders.length > 0 && (
        <Tooltip title={t('folders.move_to')}>
          <IconButton size="small" onClick={() => setMoveStream(stream)}>
            <DriveFileMoveIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      )}
      <Tooltip title={t('tracks.delete')}>
        <IconButton size="small" color="error" onClick={() => onDelete(stream)}>
          <DeleteIcon fontSize="small" />
        </IconButton>
      </Tooltip>
    </>
  );

  const mobileMenuButton = (stream: Stream) => (
    <IconButton size="small" onClick={(e) => handleMenuOpen(e, stream)}>
      <MoreVertIcon fontSize="small" />
    </IconButton>
  );

  const renderGridItem = (stream: Stream) => (
    <Box
      sx={{ height: '100%' }}
      draggable
      onDragStart={(e) => handleDragStart(e, stream)}
      onDragEnd={handleDragEnd}
    >
      <Card
        variant="outlined"
        sx={{
          borderRadius: 2,
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          opacity: draggingStreamId === stream.id ? 0.4 : 1,
          cursor: 'grab',
          transition: 'opacity 0.15s',
        }}
      >
        {stream.cover_art_url && (
          <CardMedia component="img" height="120" image={stream.cover_art_url} alt={stream.title} sx={{ objectFit: 'cover' }} />
        )}
        <CardContent sx={{ pb: 0, flex: 1 }}>
          <Typography variant="subtitle1" fontWeight={600} display="flex" alignItems="center" gap={1}>
            <StreamIcon fontSize="small" color="primary" />{stream.title}
          </Typography>
          {stream.artist && (
            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }} noWrap>{stream.artist}</Typography>
          )}
          <Box sx={{ mt: 1 }}>
            <LastPlayedCaption
              value={stream.last_played_at}
              label={t('streams.fields.last_played')}
              emptyLabel={t('never_played')}
            />
          </Box>
        </CardContent>
        <CardActions sx={{ pt: 0 }}>
          {hasInlineControls ? desktopActions(stream) : mobileMenuButton(stream)}
        </CardActions>
      </Card>
    </Box>
  );

  const renderListItem = (stream: Stream, index: number) => (
    <React.Fragment key={stream.id}>
      {index > 0 && <Divider component="li" />}
      <ListItem
        draggable
        onDragStart={(e) => handleDragStart(e, stream)}
        onDragEnd={handleDragEnd}
        secondaryAction={
          <Box display="flex" alignItems="center">
            {hasInlineControls ? desktopActions(stream) : mobileMenuButton(stream)}
          </Box>
        }
        sx={{
          pr: hasInlineControls ? LIST_ITEM_PR_DESKTOP : LIST_ITEM_PR_MOBILE,
          opacity: draggingStreamId === stream.id ? 0.4 : 1,
          cursor: 'grab',
          transition: 'opacity 0.15s',
        }}
      >
        {stream.cover_art_url ? (
          <Box component="img" src={stream.cover_art_url} alt=""
            sx={{ width: 32, height: 32, objectFit: 'cover', borderRadius: 1, mr: 1, flexShrink: 0 }} />
        ) : (
          <Box mr={1} color="text.secondary" sx={{ flexShrink: 0 }}><StreamIcon fontSize="small" /></Box>
        )}
        <ListItemText
          primary={stream.title}
          primaryTypographyProps={{ noWrap: true }}
          secondary={
            <Box component="span" display="flex" gap={1} alignItems="center" flexWrap="wrap">
              {stream.artist && <Typography component="span" variant="caption" noWrap>{stream.artist}</Typography>}
              <LastPlayedCaption
                value={stream.last_played_at}
                label={t('streams.fields.last_played')}
                emptyLabel={t('never_played')}
                separator={Boolean(stream.artist)}
              />
            </Box>
          }
        />
      </ListItem>
    </React.Fragment>
  );

  const mobileActionsMenu = (
    <Menu
      anchorEl={menuAnchor}
      open={Boolean(menuAnchor) && menuStream !== null}
      onClose={handleMenuClose}
      transformOrigin={{ horizontal: 'right', vertical: 'top' }}
      anchorOrigin={{ horizontal: 'right', vertical: 'bottom' }}
    >
      <MenuItem onClick={() => { if (menuStream) audioApi.play({ stream_id: menuStream.id }); handleMenuClose(); }}>
        <PlayArrowIcon fontSize="small" sx={{ mr: 1.5, color: 'primary.main' }} />
        {t('tracks.play')}
      </MenuItem>
      <MenuItem onClick={() => { if (menuStream) setStreamToEdit(menuStream); handleMenuClose(); }}>
        <EditIcon fontSize="small" sx={{ mr: 1.5 }} />
        {t('streams.edit')}
      </MenuItem>
      {folders.length > 0 && (
        <MenuItem onClick={() => { if (menuStream) setMoveStream(menuStream); handleMenuClose(); }}>
          <DriveFileMoveIcon fontSize="small" sx={{ mr: 1.5 }} />
          {t('folders.move_to')}
        </MenuItem>
      )}
      <Divider />
      <MenuItem onClick={() => { if (menuStream) onDelete(menuStream); handleMenuClose(); }} sx={{ color: 'error.main' }}>
        <DeleteIcon fontSize="small" sx={{ mr: 1.5 }} />
        {t('tracks.delete')}
      </MenuItem>
    </Menu>
  );

  const listPanel = (
    <Box sx={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
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

      <Box display="flex" gap={1} mb={1} alignItems="center" flexWrap="wrap">
        <ToggleButtonGroup value={viewMode} exclusive onChange={(_, v) => v && onViewModeChange(v)} size="small">
          <ToggleButton value="card" aria-label={t('view_mode_card')}><ViewModuleIcon fontSize="small" /></ToggleButton>
          <ToggleButton value="list" aria-label={t('view_mode_list')}><ViewListIcon fontSize="small" /></ToggleButton>
        </ToggleButtonGroup>

        <TextField
          placeholder={t('streams.search_placeholder')}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          size="small"
          InputProps={{ startAdornment: <InputAdornment position="start"><SearchIcon fontSize="small" /></InputAdornment> }}
          sx={{ flex: 1, minWidth: 0 }}
        />

        {hasInlineControls && sortControls}

        {!hasInlineControls && (
          <Tooltip title={t('streams.sort.open')}>
            <IconButton
              ref={filterBtnRef}
              size="small"
              onClick={() => setPopoverOpen(true)}
              aria-label={t('streams.sort.open')}
              sx={{
                overflow: 'visible',
                color: hasNonDefaultSort ? 'primary.main' : 'text.secondary',
                border: '1px solid',
                borderColor: hasNonDefaultSort ? 'primary.main' : 'divider',
                borderRadius: 1, px: 1,
              }}
            >
              <FilterListIcon fontSize="small" />
              {hasNonDefaultSort && (
                <Box component="span" sx={{
                  position: 'absolute', top: -6, right: -6,
                  width: 16, height: 16, borderRadius: '50%',
                  bgcolor: 'primary.main', color: 'primary.contrastText',
                  fontSize: '0.65rem', fontWeight: 700,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  pointerEvents: 'none',
                }}>1</Box>
              )}
            </IconButton>
          </Tooltip>
        )}
      </Box>

      {hasNonDefaultSort && (
        <Box display="flex" gap={0.75} flexWrap="wrap" mb={1.5} alignItems="center">
          <Chip size="small"
            icon={sortDir === 'asc' ? <ArrowUpwardIcon /> : <ArrowDownwardIcon />}
            label={sortKeyLabel[typedSortKey]}
            onDelete={() => onSortChange(DEFAULT_SORT_KEY, DEFAULT_SORT_DIR)}
            color="primary" variant="outlined" />
        </Box>
      )}

      <Popover
        open={popoverOpen && !hasInlineControls}
        anchorEl={filterBtnRef.current}
        onClose={() => setPopoverOpen(false)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        transformOrigin={{ vertical: 'top', horizontal: 'right' }}
        slotProps={{ paper: { sx: { mt: 0.5, borderRadius: 2, minWidth: 280 } } }}
      >
        <Paper sx={{ p: 2, display: 'flex', flexDirection: 'column', gap: 2 }}>
          <Box>
            <Typography variant="caption" color="text.secondary" fontWeight={600} display="block" mb={0.75}>
              {t('streams.sort.label')}
            </Typography>
            <Box display="flex" gap={1} alignItems="center">
              <ToggleButtonGroup value={typedSortKey} exclusive onChange={handleSortKey}
                size="small" sx={{ flex: 1, '& .MuiToggleButton-root': { flex: 1, fontSize: '0.78rem' } }}>
                <ToggleButton value="title">{t('streams.fields.title')}</ToggleButton>
                <ToggleButton value="artist">{t('streams.fields.artist')}</ToggleButton>
                <ToggleButton value="last_played_at">{t('streams.fields.last_played')}</ToggleButton>
              </ToggleButtonGroup>
              <Tooltip title={sortDir === 'asc' ? t('streams.sort.asc') : t('streams.sort.desc')}>
                <IconButton size="small" onClick={handleSortDirToggle}>
                  {sortDir === 'asc' ? <ArrowUpwardIcon fontSize="small" /> : <ArrowDownwardIcon fontSize="small" />}
                </IconButton>
              </Tooltip>
            </Box>
          </Box>
          {hasNonDefaultSort && (
            <>
              <Divider />
              <Box component="button" onClick={() => { onSortChange(DEFAULT_SORT_KEY, DEFAULT_SORT_DIR); setPopoverOpen(false); }}
                sx={{ background: 'none', border: 'none', cursor: 'pointer', color: 'text.secondary', fontSize: '0.8rem', textAlign: 'left', p: 0, '&:hover': { color: 'text.primary' } }}>
                {t('streams.sort.reset')}
              </Box>
            </>
          )}
        </Paper>
      </Popover>

      <Box sx={{ display: 'flex', flexDirection: 'column' }}>
        <Box>
          {sorted.length === 0 ? (
            <Box display="flex" justifyContent="center" py={6}>
              <Typography color="text.secondary">{t('streams.no_streams')}</Typography>
            </Box>
          ) : viewMode === 'card' ? (
            <Grid container spacing={2}>
              {paginated.map((stream) => (
                <Grid item xs={12} sm={6} lg={4} key={stream.id}>
                  {renderGridItem(stream)}
                </Grid>
              ))}
            </Grid>
          ) : (
            <List dense>
              {paginated.map((stream, index) => renderListItem(stream, index))}
            </List>
          )}
        </Box>

        {sorted.length > 0 && (
          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              flexWrap: 'wrap',
              gap: 1,
              pt: 1,
              mt: 1,
              borderTop: 1,
              borderColor: 'divider',
            }}
          >
            <ToggleButtonGroup
              size="small"
              value={pageSize}
              exclusive
              onChange={(_, v) => v && handlePageSizeChange(v)}
            >
              {PAGE_SIZE_OPTIONS.map((size) => (
                <ToggleButton key={size} value={size}>{size}</ToggleButton>
              ))}
            </ToggleButtonGroup>
            <Pagination
              size="small"
              count={totalPages}
              page={currentPage}
              onChange={(_, p) => setPage(p)}
              siblingCount={0}
            />
          </Box>
        )}
      </Box>
    </Box>
  );

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column' }}>
      {hasSplitView ? (
        <Box sx={{ display: 'flex', gap: 0 }}>
          <Box
            sx={{
              width: treeCollapsed ? TREE_COLLAPSED_WIDTH : TREE_WIDTH,
              flexShrink: 0,
              borderRight: treeCollapsed ? 1 : 0,
              borderColor: 'divider',
            }}
          >
            {treeCollapsed ? (
              <Tooltip title={t('folders.expand_tree')} placement="right">
                <IconButton
                  size="small"
                  onClick={() => onTreeCollapsedChange?.(false)}
                  sx={{ display: 'flex', mx: 'auto', mt: 1 }}
                >
                  <ChevronRightIcon fontSize="small" />
                </IconButton>
              </Tooltip>
            ) : (
              <Box sx={{ display: 'flex', flexDirection: 'column' }}>
                <Box sx={{ display: 'flex', justifyContent: 'flex-end', px: 0.5, pt: 0.5 }}>
                  <Tooltip title={t('folders.collapse_tree')}>
                    <IconButton size="small" onClick={() => onTreeCollapsedChange?.(true)}>
                      <ChevronLeftIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </Box>
                <FolderTree
                  folders={folders}
                  items={allStreams}
                  currentFolderId={currentFolderId}
                  onNavigate={handleNavigateFolder}
                  onRename={(folder) => setRenameFolder(folder as StreamFolder)}
                  onDelete={(folder) => void onFolderDelete(folder as StreamFolder)}
                  onDropItem={handleDropStreamOnFolder}
                  dragType={STREAM_DRAG_TYPE}
                  treeLabel={t('tabs.streams')}
                />
              </Box>
            )}
          </Box>
          <Box sx={{ flex: 1, minWidth: 0, pl: 2, display: 'flex', flexDirection: 'column' }}>
            {listPanel}
          </Box>
        </Box>
      ) : (
        <Box>
          {mobileView === 'tree' ? (
            <FolderTree
              folders={folders}
              items={allStreams}
              currentFolderId={currentFolderId}
              onNavigate={handleNavigateFolder}
              onRename={(folder) => setRenameFolder(folder as StreamFolder)}
              onDelete={(folder) => void onFolderDelete(folder as StreamFolder)}
              onDropItem={handleDropStreamOnFolder}
              dragType={STREAM_DRAG_TYPE}
              treeLabel={t('tabs.streams')}
            />
          ) : (
            listPanel
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

      {/* onChanged statt onSaved beim Cover-Loeschen: Liste nachziehen, aber
          auch den offenen Dialog, sonst zeigte er weiter das entfernte Bild. */}
      <StreamEditDialog
        open={!!streamToEdit}
        stream={streamToEdit}
        onClose={() => setStreamToEdit(null)}
        onSaved={(updated) => { onUpdate(updated); setStreamToEdit(null); }}
        onChanged={(updated) => { onUpdate(updated); setStreamToEdit(updated); }}
      />
    </Box>
  );
};
