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
import PodcastsIcon from '@mui/icons-material/Podcasts';
import SearchIcon from '@mui/icons-material/Search';
import ViewListIcon from '@mui/icons-material/ViewList';
import ViewModuleIcon from '@mui/icons-material/ViewModule';
import { useTranslation } from 'react-i18next';
import { audioApi } from '@/api/audio';
import { LastPlayedCaption } from '@/components/media/LastPlayedCaption';
import { PodcastEditDialog } from '@/components/media/PodcastEditDialog';
import { FolderCreateDialog } from './FolderCreateDialog';
import { FolderTree } from './FolderTree';
import type { Podcast, PodcastFolder } from '@/types/api';
import { useLayout } from '@/hooks/useLayout';

type SortKey = 'title' | 'last_fetched_at' | 'last_played_at';

const DEFAULT_SORT_KEY: SortKey = 'title';
const DEFAULT_SORT_DIR = 'asc' as const;

const TREE_WIDTH = 220;
const TREE_COLLAPSED_WIDTH = 36;
const PAGE_SIZE_OPTIONS = [25, 50] as const;
const DEFAULT_PAGE_SIZE = 25;

/** MIME type used for DnD transfer of a podcast ID */
const PODCAST_DRAG_TYPE = 'application/minabox-podcast-id';

// Desktop: 4 Buttons (Play + Edit + Move + Delete) à ~32px = ~144px
const LIST_ITEM_PR_DESKTOP = '144px';
// Mobile: single MoreVert button
const LIST_ITEM_PR_MOBILE = '40px';

interface PodcastListProps {
  podcasts: Podcast[];
  allPodcasts: Podcast[];
  folders: PodcastFolder[];
  currentFolderId: number | null;
  onNavigateFolder: (folderId: number | null) => void;
  onFolderCreate: (name: string, parentId: number | null) => Promise<void>;
  onFolderRename: (folder: PodcastFolder, name: string) => Promise<void>;
  onFolderDelete: (folder: PodcastFolder) => Promise<void>;
  onMovePodcastToFolder: (podcast: Podcast, folderId: number | null) => Promise<void>;
  onDelete: (podcast: Podcast) => void;
  onUpdate: (podcast: Podcast) => void;
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

export const PodcastList: React.FC<PodcastListProps> = ({
  podcasts,
  allPodcasts,
  folders,
  currentFolderId,
  onNavigateFolder,
  onFolderCreate,
  onFolderRename,
  onFolderDelete,
  onMovePodcastToFolder,
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
  const [podcastToEdit, setPodcastToEdit] = useState<Podcast | null>(null);

  const [createFolderOpen, setCreateFolderOpen] = useState(false);
  const [renameFolder, setRenameFolder] = useState<PodcastFolder | null>(null);
  const [movePodcast, setMovePodcast] = useState<Podcast | null>(null);

  const [menuAnchor, setMenuAnchor] = useState<HTMLElement | null>(null);
  const [menuPodcast, setMenuPodcast] = useState<Podcast | null>(null);

  const [mobileView, setMobileView] = useState<'tree' | 'list'>(
    currentFolderId === null ? 'tree' : 'list'
  );

  const [draggingPodcastId, setDraggingPodcastId] = useState<number | null>(null);
  const [page, setPage] = useState(1);

  useEffect(() => {
    onRegisterCreateFolder?.(() => setCreateFolderOpen(true));
  }, [onRegisterCreateFolder]);

  const typedSortKey = sortKey as SortKey;
  const hasNonDefaultSort = typedSortKey !== DEFAULT_SORT_KEY || sortDir !== DEFAULT_SORT_DIR;

  const sortKeyLabel: Record<SortKey, string> = {
    title: t('podcasts.fields.title'),
    last_played_at: t('podcasts.fields.last_played'),
    last_fetched_at: t('podcasts.fields.last_fetched'),
  };

  const podcastsInCurrentFolder = podcasts.filter((p) =>
    currentFolderId === null ? p.folder_id == null : p.folder_id === currentFolderId
  );

  const filtered = podcastsInCurrentFolder.filter((p) => {
    const q = search.toLowerCase();
    return p.title.toLowerCase().includes(q) || (p.description ?? '').toLowerCase().includes(q);
  });

  const sorted = [...filtered].sort((a, b) => {
    let aVal: string | number;
    let bVal: string | number;
    if (typedSortKey === 'last_fetched_at') {
      aVal = a.last_fetched_at ? new Date(a.last_fetched_at).getTime() : 0;
      bVal = b.last_fetched_at ? new Date(b.last_fetched_at).getTime() : 0;
    } else if (typedSortKey === 'last_played_at') {
      aVal = a.last_played_at ? new Date(a.last_played_at).getTime() : 0;
      bVal = b.last_played_at ? new Date(b.last_played_at).getTime() : 0;
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

  const handleMenuOpen = (e: React.MouseEvent<HTMLElement>, podcast: Podcast) => {
    e.stopPropagation();
    setMenuAnchor(e.currentTarget);
    setMenuPodcast(podcast);
  };

  const handleMenuClose = () => {
    setMenuAnchor(null);
    setMenuPodcast(null);
  };

  // --- Drag & Drop helpers ---
  const handleDragStart = (e: React.DragEvent, podcast: Podcast) => {
    e.dataTransfer.setData(PODCAST_DRAG_TYPE, String(podcast.id));
    e.dataTransfer.effectAllowed = 'move';
    setDraggingPodcastId(podcast.id);
  };

  const handleDragEnd = () => setDraggingPodcastId(null);

  const handleDropPodcastOnFolder = (podcastId: number, targetFolderId: number | null) => {
    const podcast = allPodcasts.find((p) => p.id === podcastId);
    if (podcast) {
      void onMovePodcastToFolder(podcast, targetFolderId);
    }
  };

  const MoveMenu = movePodcast ? (
    <Popover
      open
      onClose={() => setMovePodcast(null)}
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
          onClick={() => { void onMovePodcastToFolder(movePodcast, null); setMovePodcast(null); }}
          sx={{ display: 'block', width: '100%', textAlign: 'left', background: 'none', border: 'none', cursor: 'pointer', px: 2, py: 0.75, borderRadius: 1, fontSize: '0.875rem', '&:hover': { bgcolor: 'action.hover' } }}
        >
          📁 {t('folders.root')}
        </Box>
      )}
      {folders.map((f) => f.id !== currentFolderId && (
        <Box
          key={f.id}
          component="button"
          onClick={() => { void onMovePodcastToFolder(movePodcast, f.id); setMovePodcast(null); }}
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
        <ToggleButton value="title">{t('podcasts.fields.title')}</ToggleButton>
        <ToggleButton value="last_played_at">{t('podcasts.fields.last_played')}</ToggleButton>
        <ToggleButton value="last_fetched_at">{t('podcasts.fields.last_fetched')}</ToggleButton>
      </ToggleButtonGroup>
      <Tooltip title={sortDir === 'asc' ? t('podcasts.sort.asc') : t('podcasts.sort.desc')}>
        <IconButton size="small" onClick={handleSortDirToggle}>
          {sortDir === 'asc' ? <ArrowUpwardIcon fontSize="small" /> : <ArrowDownwardIcon fontSize="small" />}
        </IconButton>
      </Tooltip>
    </Box>
  );

  const desktopActions = (podcast: Podcast) => (
    <>
      <Tooltip title={t('tracks.play')}>
        <IconButton size="small" color="primary" onClick={() => audioApi.play({ podcast_id: podcast.id })}>
          <PlayArrowIcon fontSize="small" />
        </IconButton>
      </Tooltip>
      <Tooltip title={t('podcasts.edit')}>
        <IconButton size="small" onClick={() => setPodcastToEdit(podcast)}>
          <EditIcon fontSize="small" />
        </IconButton>
      </Tooltip>
      {folders.length > 0 && (
        <Tooltip title={t('folders.move_to')}>
          <IconButton size="small" onClick={() => setMovePodcast(podcast)}>
            <DriveFileMoveIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      )}
      <Tooltip title={t('tracks.delete')}>
        <IconButton size="small" color="error" onClick={() => onDelete(podcast)}>
          <DeleteIcon fontSize="small" />
        </IconButton>
      </Tooltip>
    </>
  );

  const mobileMenuButton = (podcast: Podcast) => (
    <IconButton size="small" onClick={(e) => handleMenuOpen(e, podcast)}>
      <MoreVertIcon fontSize="small" />
    </IconButton>
  );

  const renderGridItem = (podcast: Podcast) => (
    <Box
      sx={{ height: '100%' }}
      draggable
      onDragStart={(e) => handleDragStart(e, podcast)}
      onDragEnd={handleDragEnd}
    >
      <Card
        variant="outlined"
        sx={{
          borderRadius: 2,
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          opacity: draggingPodcastId === podcast.id ? 0.4 : 1,
          cursor: 'grab',
          transition: 'opacity 0.15s',
        }}
      >
        {podcast.cover_art_url && (
          <CardMedia component="img" height="120" image={podcast.cover_art_url} alt={podcast.title} sx={{ objectFit: 'cover' }} />
        )}
        <CardContent sx={{ pb: 0, flex: 1 }}>
          <Typography variant="subtitle1" fontWeight={600} display="flex" alignItems="center" gap={1}>
            <PodcastsIcon fontSize="small" color="primary" />{podcast.title}
          </Typography>
          {podcast.latest_episode_title && (
            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }} noWrap>
              {t('podcasts.latest_episode')}: {podcast.latest_episode_title}
            </Typography>
          )}
        </CardContent>
        <CardActions sx={{ pt: 0 }}>
          {hasInlineControls ? desktopActions(podcast) : mobileMenuButton(podcast)}
        </CardActions>
      </Card>
    </Box>
  );

  const renderListItem = (podcast: Podcast, index: number) => (
    <React.Fragment key={podcast.id}>
      {index > 0 && <Divider component="li" />}
      <ListItem
        draggable
        onDragStart={(e) => handleDragStart(e, podcast)}
        onDragEnd={handleDragEnd}
        secondaryAction={
          <Box display="flex" alignItems="center">
            {hasInlineControls ? desktopActions(podcast) : mobileMenuButton(podcast)}
          </Box>
        }
        sx={{
          pr: hasInlineControls ? LIST_ITEM_PR_DESKTOP : LIST_ITEM_PR_MOBILE,
          opacity: draggingPodcastId === podcast.id ? 0.4 : 1,
          cursor: 'grab',
          transition: 'opacity 0.15s',
        }}
      >
        {podcast.cover_art_url ? (
          <Box component="img" src={podcast.cover_art_url} alt=""
            sx={{ width: 32, height: 32, objectFit: 'cover', borderRadius: 1, mr: 1, flexShrink: 0 }} />
        ) : (
          <Box mr={1} color="text.secondary" sx={{ flexShrink: 0 }}><PodcastsIcon fontSize="small" /></Box>
        )}
        <ListItemText
          primary={podcast.title}
          primaryTypographyProps={{ noWrap: true }}
          secondary={
            <Box component="span" display="flex" flexDirection="column" gap={0.25}>
              {podcast.latest_episode_title && (
                <Typography component="span" variant="caption" display="block" noWrap>
                  {t('podcasts.latest_episode')}: {podcast.latest_episode_title}
                  {podcast.latest_episode_published_at &&
                    ` (${new Date(podcast.latest_episode_published_at).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })})`}
                </Typography>
              )}
              <Box component="span" display="flex" gap={1} flexWrap="wrap" alignItems="center">
                <LastPlayedCaption
                  value={podcast.last_played_at}
                  label={t('podcasts.last_played')}
                  emptyLabel={t('never_played')}
                />
                <LastPlayedCaption
                  value={podcast.last_fetched_at}
                  label={t('podcasts.last_fetched_label')}
                  separator
                />
              </Box>
            </Box>
          }
        />
      </ListItem>
    </React.Fragment>
  );

  const mobileActionsMenu = (
    <Menu
      anchorEl={menuAnchor}
      open={Boolean(menuAnchor) && menuPodcast !== null}
      onClose={handleMenuClose}
      transformOrigin={{ horizontal: 'right', vertical: 'top' }}
      anchorOrigin={{ horizontal: 'right', vertical: 'bottom' }}
    >
      <MenuItem onClick={() => { if (menuPodcast) audioApi.play({ podcast_id: menuPodcast.id }); handleMenuClose(); }}>
        <PlayArrowIcon fontSize="small" sx={{ mr: 1.5, color: 'primary.main' }} />
        {t('tracks.play')}
      </MenuItem>
      <MenuItem onClick={() => { if (menuPodcast) setPodcastToEdit(menuPodcast); handleMenuClose(); }}>
        <EditIcon fontSize="small" sx={{ mr: 1.5 }} />
        {t('podcasts.edit')}
      </MenuItem>
      {folders.length > 0 && (
        <MenuItem onClick={() => { if (menuPodcast) setMovePodcast(menuPodcast); handleMenuClose(); }}>
          <DriveFileMoveIcon fontSize="small" sx={{ mr: 1.5 }} />
          {t('folders.move_to')}
        </MenuItem>
      )}
      <Divider />
      <MenuItem onClick={() => { if (menuPodcast) onDelete(menuPodcast); handleMenuClose(); }} sx={{ color: 'error.main' }}>
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
          placeholder={t('podcasts.search_placeholder')}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          size="small"
          InputProps={{ startAdornment: <InputAdornment position="start"><SearchIcon fontSize="small" /></InputAdornment> }}
          sx={{ flex: 1, minWidth: 0 }}
        />

        {hasInlineControls && sortControls}

        {!hasInlineControls && (
          <Tooltip title={t('podcasts.sort.open')}>
            <IconButton
              ref={filterBtnRef}
              size="small"
              onClick={() => setPopoverOpen(true)}
              aria-label={t('podcasts.sort.open')}
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
              {t('podcasts.sort.label')}
            </Typography>
            <Box display="flex" gap={1} alignItems="center">
              <ToggleButtonGroup value={typedSortKey} exclusive onChange={handleSortKey}
                size="small" sx={{ flex: 1, '& .MuiToggleButton-root': { flex: 1, fontSize: '0.78rem' } }}>
                <ToggleButton value="title">{t('podcasts.fields.title')}</ToggleButton>
                <ToggleButton value="last_played_at">{t('podcasts.fields.last_played')}</ToggleButton>
                <ToggleButton value="last_fetched_at">{t('podcasts.fields.last_fetched')}</ToggleButton>
              </ToggleButtonGroup>
              <Tooltip title={sortDir === 'asc' ? t('podcasts.sort.asc') : t('podcasts.sort.desc')}>
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
                {t('podcasts.sort.reset')}
              </Box>
            </>
          )}
        </Paper>
      </Popover>

      <Box sx={{ display: 'flex', flexDirection: 'column' }}>
        <Box>
          {sorted.length === 0 ? (
            <Box display="flex" justifyContent="center" py={6}>
              <Typography color="text.secondary">{t('podcasts.no_podcasts')}</Typography>
            </Box>
          ) : viewMode === 'card' ? (
            <Grid container spacing={2}>
              {paginated.map((podcast) => (
                <Grid item xs={12} sm={6} lg={4} key={podcast.id}>
                  {renderGridItem(podcast)}
                </Grid>
              ))}
            </Grid>
          ) : (
            <List dense>
              {paginated.map((podcast, index) => renderListItem(podcast, index))}
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
                  items={allPodcasts}
                  currentFolderId={currentFolderId}
                  onNavigate={handleNavigateFolder}
                  onRename={(folder) => setRenameFolder(folder as PodcastFolder)}
                  onDelete={(folder) => void onFolderDelete(folder as PodcastFolder)}
                  onDropItem={handleDropPodcastOnFolder}
                  dragType={PODCAST_DRAG_TYPE}
                  treeLabel={t('tabs.podcasts')}
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
              items={allPodcasts}
              currentFolderId={currentFolderId}
              onNavigate={handleNavigateFolder}
              onRename={(folder) => setRenameFolder(folder as PodcastFolder)}
              onDelete={(folder) => void onFolderDelete(folder as PodcastFolder)}
              onDropItem={handleDropPodcastOnFolder}
              dragType={PODCAST_DRAG_TYPE}
              treeLabel={t('tabs.podcasts')}
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

      <PodcastEditDialog
        open={!!podcastToEdit}
        podcast={podcastToEdit}
        onClose={() => setPodcastToEdit(null)}
        onSuccess={(updated) => { onUpdate(updated); setPodcastToEdit(null); }}
      />
    </Box>
  );
};
