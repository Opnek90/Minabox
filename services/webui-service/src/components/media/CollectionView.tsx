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
import DriveFileMoveIcon from '@mui/icons-material/DriveFileMove';
import FilterListIcon from '@mui/icons-material/FilterList';
import MoreVertIcon from '@mui/icons-material/MoreVert';
import SearchIcon from '@mui/icons-material/Search';
import ViewColumnIcon from '@mui/icons-material/ViewColumn';
import ViewListIcon from '@mui/icons-material/ViewList';
import ViewModuleIcon from '@mui/icons-material/ViewModule';
import { useTranslation } from 'react-i18next';
import { DetailsTable, type DetailsColumn } from './DetailsTable';
import { FolderCreateDialog } from './FolderCreateDialog';
import { FolderTree, type MediaFolder } from './FolderTree';
import type { ViewMode } from '@/contexts/UserPrefsContext';
import { useLayout } from '@/hooks/useLayout';

/** Everything a collection item must offer so the generic view can work with it. */
export interface CollectionItem {
  id: number;
  title: string;
  folder_id?: number | null;
  cover_art_url?: string | null;
}

/** One entry of the sort toggle group. */
export interface CollectionSortOption<T> {
  /** Doubles as the stored sort key and as the `DetailsTable` column key. */
  key: string;
  label: string;
  /** Comparable value - lower-case strings for text, epoch millis for dates. */
  value: (item: T) => string | number;
}

/**
 * One row action - shown as an icon button on wide layouts, as a menu entry
 * below. "Move to folder" is not part of this list: the view owns the folder
 * popover and inserts that action itself, right before the destructive ones.
 */
export interface CollectionAction<T> {
  key: string;
  label: string;
  icon: React.ReactNode;
  onClick: (item: T) => void;
  /** `false` drops the action entirely (no folders, no playlists, no edit handler). */
  available?: boolean;
  /** Rendered in the primary colour (play). */
  primary?: boolean;
  /** Rendered in red and separated from the rest in the mobile menu (delete). */
  destructive?: boolean;
}

/** Optional extra filter above the sort controls - so far only tracks have one. */
export interface CollectionFilter<T> {
  value: string;
  defaultValue: string;
  onChange: (value: string) => void;
  label: string;
  options: { value: string; label: string }[];
  matches: (item: T, value: string) => boolean;
}

/**
 * The per-type half of a collection: what the items look like, how they are
 * searched and sorted, and what can be done with them. Everything else -
 * folder tree, toolbar, paging, drag & drop - lives in `CollectionView`.
 */
export interface CollectionDescriptor<T extends CollectionItem> {
  /** MIME type of the DnD payload, e.g. 'application/minabox-track-id'. */
  dragType: string;
  /** Heading above the folder tree, usually the tab name. */
  treeLabel: string;
  searchPlaceholder: string;
  emptyText: string;
  sortLabel: string;
  /** Tooltip of the popover button that replaces the inline controls. */
  sortOpenLabel: string;
  sortAscLabel: string;
  sortDescLabel: string;
  /** Label of the "reset" link at the bottom of the popover. */
  resetLabel: string;
  sortOptions: CollectionSortOption<T>[];
  defaultSortKey: string;
  /** Haystack for the free-text search. */
  searchFields: (item: T) => (string | null | undefined)[];
  /** Leading thumbnail; `size` is 28 in the details view, 32 in the list. */
  renderThumbnail: (item: T, size: number) => React.ReactNode;
  /** Small icon in front of the title on a card. */
  renderIcon: (item: T) => React.ReactNode;
  /** Everything below the title on a card. */
  renderCardBody: (item: T) => React.ReactNode;
  /** Secondary line(s) of a list row. */
  renderListSecondary: (item: T) => React.ReactNode;
  columns: DetailsColumn<T>[];
  actions: CollectionAction<T>[];
  filter?: CollectionFilter<T>;
}

interface CollectionViewProps<T extends CollectionItem> {
  items: T[];
  folders: MediaFolder[];
  currentFolderId: number | null;
  onNavigateFolder: (folderId: number | null) => void;
  onFolderCreate: (name: string, parentId: number | null) => Promise<void>;
  onFolderRename: (folder: MediaFolder, name: string) => Promise<void>;
  onFolderDelete: (folder: MediaFolder) => Promise<void>;
  onMoveToFolder: (item: T, folderId: number | null) => Promise<void>;
  sortKey: string;
  sortDir: 'asc' | 'desc';
  onSortChange: (key: string, dir: 'asc' | 'desc') => void;
  viewMode: ViewMode;
  onViewModeChange: (mode: ViewMode) => void;
  treeCollapsed?: boolean;
  onTreeCollapsedChange?: (collapsed: boolean) => void;
  pageSize?: number;
  onPageSizeChange?: (size: number) => void;
  onRegisterCreateFolder?: (fn: () => void) => void;
  descriptor: CollectionDescriptor<T>;
}

const DEFAULT_SORT_DIR = 'asc' as const;

const TREE_WIDTH = 220;
const TREE_COLLAPSED_WIDTH = 36;
const PAGE_SIZE_OPTIONS = [25, 50] as const;
const DEFAULT_PAGE_SIZE = 25;

/** Width of one icon button, so the list row leaves room for its actions. */
const ACTION_BUTTON_WIDTH = 36;
/** Mobile shows a single MoreVert button instead. */
const LIST_ITEM_PR_MOBILE = '40px';

export function CollectionView<T extends CollectionItem>({
  items,
  folders,
  currentFolderId,
  onNavigateFolder,
  onFolderCreate,
  onFolderRename,
  onFolderDelete,
  onMoveToFolder,
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
  descriptor,
}: CollectionViewProps<T>) {
  const { t } = useTranslation('media');
  const theme = useTheme();
  // Two questions that used to hang off the same boundary and were therefore
  // both answered wrongly on tablets:
  // (1) Is there room for sorting, filters and row actions in the bar?
  //     Yes from tablet up - 834px is plenty for that.
  const layout = useLayout();
  const hasInlineControls = layout.hasRoomForInlineControls;
  // (2) Do the folder tree and the list fit side by side? The tree takes a
  //     fixed 220px; below that too little would remain for the list, so the
  //     master-detail switch deliberately stays at 900px, not the tablet edge.
  const hasSplitView = useMediaQuery(theme.breakpoints.up('md'));
  // The details view needs real width for its columns, so it stays desktop-only
  // (issue #115). Below that a stored "details" preference falls back to the
  // list view without being overwritten.
  const effectiveViewMode: ViewMode =
    viewMode === 'details' && !layout.isDesktop ? 'list' : viewMode;

  const filterBtnRef = useRef<HTMLButtonElement>(null);
  const [popoverOpen, setPopoverOpen] = useState(false);
  const [search, setSearch] = useState('');

  const [createFolderOpen, setCreateFolderOpen] = useState(false);
  const [renameFolder, setRenameFolder] = useState<MediaFolder | null>(null);
  const [moveItem, setMoveItem] = useState<T | null>(null);

  const [menuAnchor, setMenuAnchor] = useState<HTMLElement | null>(null);
  const [menuItemTarget, setMenuItemTarget] = useState<T | null>(null);

  const [mobileView, setMobileView] = useState<'tree' | 'list'>(
    currentFolderId === null ? 'tree' : 'list'
  );

  const [draggingId, setDraggingId] = useState<number | null>(null);
  const [page, setPage] = useState(1);

  useEffect(() => {
    onRegisterCreateFolder?.(() => setCreateFolderOpen(true));
  }, [onRegisterCreateFolder]);

  const { filter, sortOptions, actions } = descriptor;
  const activeSort =
    sortOptions.find((o) => o.key === sortKey) ??
    sortOptions.find((o) => o.key === descriptor.defaultSortKey) ??
    sortOptions[0];

  const hasActiveFilter = filter !== undefined && filter.value !== filter.defaultValue;
  const hasNonDefaultSort = sortKey !== descriptor.defaultSortKey || sortDir !== DEFAULT_SORT_DIR;
  const hasAnyActiveChip = hasActiveFilter || hasNonDefaultSort;
  const activeBadgeCount = (hasActiveFilter ? 1 : 0) + (hasNonDefaultSort ? 1 : 0);

  // "Move to folder" is generic and needs the popover below, so it is not part
  // of the descriptor. It goes where all three lists used to have it: after the
  // type-specific actions, before delete.
  const moveAction: CollectionAction<T> = {
    key: 'move',
    label: t('folders.move_to'),
    icon: <DriveFileMoveIcon fontSize="small" />,
    onClick: (item) => setMoveItem(item),
    available: folders.length > 0,
  };
  const visibleActions = [
    ...actions.filter((a) => !a.destructive),
    moveAction,
    ...actions.filter((a) => a.destructive),
  ].filter((a) => a.available !== false);

  const inCurrentFolder = items.filter((item) =>
    currentFolderId === null ? item.folder_id == null : item.folder_id === currentFolderId
  );

  const query = search.toLowerCase();
  const filtered = inCurrentFolder.filter((item) => {
    const matchesSearch = descriptor
      .searchFields(item)
      .some((field) => (field ?? '').toLowerCase().includes(query));
    const matchesFilter = !filter || filter.matches(item, filter.value);
    return matchesSearch && matchesFilter;
  });

  const sorted = [...filtered].sort((a, b) => {
    const aVal = activeSort.value(a);
    const bVal = activeSort.value(b);
    if (aVal < bVal) return sortDir === 'asc' ? -1 : 1;
    if (aVal > bVal) return sortDir === 'asc' ? 1 : -1;
    return 0;
  });

  const totalPages = Math.max(1, Math.ceil(sorted.length / pageSize));
  const currentPage = Math.min(page, totalPages);
  const paginated = sorted.slice((currentPage - 1) * pageSize, currentPage * pageSize);

  useEffect(() => {
    setPage(1);
  }, [search, filter?.value, sortKey, sortDir, currentFolderId, pageSize]);

  const handleSortKey = (_: React.MouseEvent, key: string | null) => {
    if (!key) return;
    if (key === sortKey) onSortChange(key, sortDir === 'asc' ? 'desc' : 'asc');
    else onSortChange(key, 'asc');
  };

  const handleSortDirToggle = () => onSortChange(sortKey, sortDir === 'asc' ? 'desc' : 'asc');

  const handleResetAll = () => {
    filter?.onChange(filter.defaultValue);
    onSortChange(descriptor.defaultSortKey, DEFAULT_SORT_DIR);
  };

  const handleNavigateFolder = (folderId: number | null) => {
    onNavigateFolder(folderId);
    if (!hasSplitView) setMobileView('list');
  };

  const handleMenuOpen = (e: React.MouseEvent<HTMLElement>, item: T) => {
    e.stopPropagation();
    setMenuAnchor(e.currentTarget);
    setMenuItemTarget(item);
  };

  const handleMenuClose = () => {
    setMenuAnchor(null);
    setMenuItemTarget(null);
  };

  // --- Drag & Drop helpers ---
  const handleDragStart = (e: React.DragEvent, item: T) => {
    e.dataTransfer.setData(descriptor.dragType, String(item.id));
    e.dataTransfer.effectAllowed = 'move';
    setDraggingId(item.id);
  };

  const handleDragEnd = () => setDraggingId(null);

  /**
   * Called by FolderTree when an item is dropped onto a folder node.
   * Looks the full item up and delegates to onMoveToFolder.
   */
  const handleDropOnFolder = (itemId: number, targetFolderId: number | null) => {
    const item = items.find((i) => i.id === itemId);
    if (item) void onMoveToFolder(item, targetFolderId);
  };

  const moveMenu = moveItem ? (
    <Popover
      open
      onClose={() => setMoveItem(null)}
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
          onClick={() => { void onMoveToFolder(moveItem, null); setMoveItem(null); }}
          sx={{ display: 'block', width: '100%', textAlign: 'left', background: 'none', border: 'none', cursor: 'pointer', px: 2, py: 0.75, borderRadius: 1, fontSize: '0.875rem', '&:hover': { bgcolor: 'action.hover' } }}
        >
          📁 {t('folders.root')}
        </Box>
      )}
      {folders.map((f) => f.id !== currentFolderId && (
        <Box
          key={f.id}
          component="button"
          onClick={() => { void onMoveToFolder(moveItem, f.id); setMoveItem(null); }}
          sx={{ display: 'block', width: '100%', textAlign: 'left', background: 'none', border: 'none', cursor: 'pointer', px: 2, py: 0.75, borderRadius: 1, fontSize: '0.875rem', '&:hover': { bgcolor: 'action.hover' } }}
        >
          📂 {f.name}
        </Box>
      ))}
    </Popover>
  ) : null;

  const filterControls = filter && (
    <ToggleButtonGroup
      value={filter.value}
      exclusive
      onChange={(_, v) => v && filter.onChange(v)}
      size="small"
    >
      {filter.options.map((o) => (
        <ToggleButton key={o.value} value={o.value}>{o.label}</ToggleButton>
      ))}
    </ToggleButtonGroup>
  );

  const sortToggleGroup = (sx?: object) => (
    <ToggleButtonGroup value={sortKey} exclusive onChange={handleSortKey} size="small" sx={sx}>
      {sortOptions.map((o) => (
        <ToggleButton key={o.key} value={o.key}>{o.label}</ToggleButton>
      ))}
    </ToggleButtonGroup>
  );

  const sortDirButton = (
    <Tooltip title={sortDir === 'asc' ? descriptor.sortAscLabel : descriptor.sortDescLabel}>
      <IconButton size="small" onClick={handleSortDirToggle}>
        {sortDir === 'asc' ? <ArrowUpwardIcon fontSize="small" /> : <ArrowDownwardIcon fontSize="small" />}
      </IconButton>
    </Tooltip>
  );

  const sortControls = (
    <Box display="flex" alignItems="center" gap={0.5}>
      {sortToggleGroup()}
      {sortDirButton}
    </Box>
  );

  /** Full row action set for wide layouts (list secondary action + details view). */
  const rowActions = (item: T) => (
    <>
      {visibleActions.map((action) => (
        <Tooltip key={action.key} title={action.label}>
          <IconButton
            size="small"
            color={action.primary ? 'primary' : action.destructive ? 'error' : undefined}
            onClick={() => action.onClick(item)}
          >
            {action.icon}
          </IconButton>
        </Tooltip>
      ))}
    </>
  );

  const mobileMenuButton = (item: T) => (
    <IconButton size="small" onClick={(e) => handleMenuOpen(e, item)}>
      <MoreVertIcon fontSize="small" />
    </IconButton>
  );

  const renderGridItem = (item: T) => (
    <Box
      sx={{ height: '100%' }}
      draggable
      onDragStart={(e) => handleDragStart(e, item)}
      onDragEnd={handleDragEnd}
    >
      <Card
        variant="outlined"
        sx={{
          borderRadius: 2,
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          opacity: draggingId === item.id ? 0.4 : 1,
          cursor: 'grab',
          transition: 'opacity 0.15s',
        }}
      >
        {item.cover_art_url && (
          <CardMedia component="img" height="120" image={item.cover_art_url} alt={item.title} sx={{ objectFit: 'cover' }} />
        )}
        <CardContent sx={{ pb: 0, flex: 1 }}>
          <Typography variant="subtitle1" fontWeight={600} display="flex" alignItems="center" gap={1}>
            {descriptor.renderIcon(item)}
            {item.title}
          </Typography>
          {descriptor.renderCardBody(item)}
        </CardContent>
        <CardActions sx={{ pt: 0 }}>
          {hasInlineControls ? rowActions(item) : mobileMenuButton(item)}
        </CardActions>
      </Card>
    </Box>
  );

  const renderListItem = (item: T, index: number) => (
    <ListItem
      key={item.id}
      draggable
      onDragStart={(e) => handleDragStart(e, item)}
      onDragEnd={handleDragEnd}
      divider={index < paginated.length - 1}
      secondaryAction={
        <Box display="flex" alignItems="center">
          {hasInlineControls ? rowActions(item) : mobileMenuButton(item)}
        </Box>
      }
      sx={{
        pr: hasInlineControls
          ? `${visibleActions.length * ACTION_BUTTON_WIDTH}px`
          : LIST_ITEM_PR_MOBILE,
        opacity: draggingId === item.id ? 0.4 : 1,
        cursor: 'grab',
        transition: 'opacity 0.15s',
      }}
    >
      <Box sx={{ mr: 1, flexShrink: 0, display: 'flex' }}>
        {descriptor.renderThumbnail(item, 32)}
      </Box>
      <ListItemText
        primary={item.title}
        primaryTypographyProps={{ noWrap: true }}
        secondaryTypographyProps={{ component: 'span' }}
        secondary={descriptor.renderListSecondary(item)}
      />
    </ListItem>
  );

  const menuActions = visibleActions.filter((a) => !a.destructive);
  const menuDestructiveActions = visibleActions.filter((a) => a.destructive);

  const mobileActionsMenu = (
    <Menu
      anchorEl={menuAnchor}
      open={Boolean(menuAnchor) && menuItemTarget !== null}
      onClose={handleMenuClose}
      transformOrigin={{ horizontal: 'right', vertical: 'top' }}
      anchorOrigin={{ horizontal: 'right', vertical: 'bottom' }}
    >
      {menuActions.map((action) => (
        <MenuItem
          key={action.key}
          onClick={() => { if (menuItemTarget) action.onClick(menuItemTarget); handleMenuClose(); }}
        >
          <Box sx={{ mr: 1.5, display: 'flex', color: action.primary ? 'primary.main' : undefined }}>
            {action.icon}
          </Box>
          {action.label}
        </MenuItem>
      ))}
      {menuDestructiveActions.length > 0 && <Divider />}
      {menuDestructiveActions.map((action) => (
        <MenuItem
          key={action.key}
          onClick={() => { if (menuItemTarget) action.onClick(menuItemTarget); handleMenuClose(); }}
          sx={{ color: 'error.main' }}
        >
          <Box sx={{ mr: 1.5, display: 'flex' }}>{action.icon}</Box>
          {action.label}
        </MenuItem>
      ))}
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

      <Box display="flex" gap={1} mb={1} alignItems="center" flexWrap="wrap" flexShrink={0}>
        <ToggleButtonGroup value={effectiveViewMode} exclusive onChange={(_, v) => v && onViewModeChange(v)} size="small">
          <ToggleButton value="card" aria-label={t('view_mode_card')}><ViewModuleIcon fontSize="small" /></ToggleButton>
          <ToggleButton value="list" aria-label={t('view_mode_list')}><ViewListIcon fontSize="small" /></ToggleButton>
          {layout.isDesktop && (
            <ToggleButton value="details" aria-label={t('view_mode_details')}><ViewColumnIcon fontSize="small" /></ToggleButton>
          )}
        </ToggleButtonGroup>

        <TextField
          placeholder={descriptor.searchPlaceholder}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          size="small"
          InputProps={{ startAdornment: <InputAdornment position="start"><SearchIcon fontSize="small" /></InputAdornment> }}
          sx={{ flex: 1, minWidth: 0 }}
        />

        {hasInlineControls && (
          <>
            {filterControls}
            {effectiveViewMode !== 'details' && sortControls}
          </>
        )}

        {!hasInlineControls && (
          <Tooltip title={descriptor.sortOpenLabel}>
            <IconButton
              ref={filterBtnRef}
              size="small"
              onClick={() => setPopoverOpen(true)}
              aria-label={descriptor.sortOpenLabel}
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
        <Box display="flex" gap={0.75} flexWrap="wrap" mb={1.5} alignItems="center" flexShrink={0}>
          {hasActiveFilter && filter && (
            <Chip size="small"
              label={filter.options.find((o) => o.value === filter.value)?.label ?? filter.value}
              onDelete={() => filter.onChange(filter.defaultValue)}
              color="primary" variant="outlined" />
          )}
          {hasNonDefaultSort && (
            <Chip size="small"
              icon={sortDir === 'asc' ? <ArrowUpwardIcon /> : <ArrowDownwardIcon />}
              label={activeSort.label}
              onDelete={() => onSortChange(descriptor.defaultSortKey, DEFAULT_SORT_DIR)}
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
        slotProps={{ paper: { sx: { mt: 0.5, borderRadius: 2, minWidth: filter ? 300 : 280 } } }}
      >
        <Paper sx={{ p: 2, display: 'flex', flexDirection: 'column', gap: 2 }}>
          {filter && (
            <>
              <Box>
                <Typography variant="caption" color="text.secondary" fontWeight={600} display="block" mb={0.75}>
                  {filter.label}
                </Typography>
                <ToggleButtonGroup value={filter.value} exclusive onChange={(_, v) => v && filter.onChange(v)}
                  size="small" fullWidth sx={{ '& .MuiToggleButton-root': { flex: 1, fontSize: '0.78rem' } }}>
                  {filter.options.map((o) => (
                    <ToggleButton key={o.value} value={o.value}>{o.label}</ToggleButton>
                  ))}
                </ToggleButtonGroup>
              </Box>
              <Divider />
            </>
          )}
          <Box>
            <Typography variant="caption" color="text.secondary" fontWeight={600} display="block" mb={0.75}>
              {descriptor.sortLabel}
            </Typography>
            <Box display="flex" gap={1} alignItems="center">
              {sortToggleGroup({
                flex: 1,
                // Four sort keys no longer fit at 0.78rem inside the popover.
                '& .MuiToggleButton-root': {
                  flex: 1,
                  fontSize: sortOptions.length > 3 ? '0.7rem' : '0.78rem',
                },
              })}
              {sortDirButton}
            </Box>
          </Box>
          {hasAnyActiveChip && (
            <>
              <Divider />
              <Box component="button"
                onClick={() => { handleResetAll(); setPopoverOpen(false); }}
                sx={{ background: 'none', border: 'none', cursor: 'pointer', color: 'text.secondary', fontSize: '0.8rem', textAlign: 'left', p: 0, '&:hover': { color: 'text.primary' } }}>
                {descriptor.resetLabel}
              </Box>
            </>
          )}
        </Paper>
      </Popover>

      <Box sx={{ display: 'flex', flexDirection: 'column' }}>
        <Box>
          {sorted.length === 0 ? (
            <Box display="flex" justifyContent="center" py={6}>
              <Typography color="text.secondary">{descriptor.emptyText}</Typography>
            </Box>
          ) : effectiveViewMode === 'card' ? (
            <Grid container spacing={2}>
              {paginated.map((item) => (
                <Grid item xs={12} sm={6} lg={4} key={item.id}>
                  {renderGridItem(item)}
                </Grid>
              ))}
            </Grid>
          ) : effectiveViewMode === 'details' ? (
            <DetailsTable<T>
              items={paginated}
              columns={descriptor.columns}
              sortKey={sortKey}
              sortDir={sortDir}
              onSortChange={onSortChange}
              rowKey={(item) => item.id}
              emptyText={descriptor.emptyText}
              renderActions={rowActions}
              onRowDragStart={handleDragStart}
              onRowDragEnd={handleDragEnd}
              draggingKey={draggingId}
            />
          ) : (
            <List dense>
              {paginated.map((item, index) => renderListItem(item, index))}
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
              flexShrink: 0,
              borderTop: 1,
              borderColor: 'divider',
            }}
          >
            <ToggleButtonGroup
              size="small"
              value={pageSize}
              exclusive
              onChange={(_, v) => v && onPageSizeChange?.(v)}
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

  const folderTree = (
    <FolderTree
      folders={folders}
      items={items}
      currentFolderId={currentFolderId}
      onNavigate={handleNavigateFolder}
      onRename={setRenameFolder}
      onDelete={(folder) => void onFolderDelete(folder)}
      onDropItem={handleDropOnFolder}
      dragType={descriptor.dragType}
      treeLabel={descriptor.treeLabel}
    />
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
                {folderTree}
              </Box>
            )}
          </Box>
          <Box sx={{ flex: 1, minWidth: 0, pl: 2, display: 'flex', flexDirection: 'column' }}>
            {listPanel}
          </Box>
        </Box>
      ) : (
        <Box>{mobileView === 'tree' ? folderTree : listPanel}</Box>
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

      {moveMenu}
      {mobileActionsMenu}
    </Box>
  );
}
