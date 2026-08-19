import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Alert,
  Box,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  Divider,
  IconButton,
  InputAdornment,
  Paper,
  Popover,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Tooltip,
  Typography,
} from '@mui/material';
import ArrowDownwardIcon from '@mui/icons-material/ArrowDownward';
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward';
import FilterListIcon from '@mui/icons-material/FilterList';
import SearchIcon from '@mui/icons-material/Search';
import ViewListIcon from '@mui/icons-material/ViewList';
import ViewModuleIcon from '@mui/icons-material/ViewModule';
import { useTranslation } from 'react-i18next';
import { ActionButton } from '@/components/ui/ActionButton';
import { TagList } from '@/components/rfid/TagList';
import { TagEditDialog } from '@/components/rfid/TagEditDialog';
import { LearnModeButton } from '@/components/rfid/LearnModeButton';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { PageShell } from '@/components/common/PageShell';
import { useToast } from '@/contexts/ToastContext';
import { useUserPrefs } from '@/contexts/UserPrefsContext';
import { tagsApi } from '@/api/tags';
import { playlistsApi } from '@/api/playlists';
import { podcastsApi } from '@/api/podcasts';
import { streamsApi } from '@/api/streams';
import { tracksApi } from '@/api/tracks';
import { useWebSocketEvent } from '@/contexts/WebSocketContext';
import type { Tag, Playlist, Podcast, Stream, Track, ContentType, RFIDScannedMessage } from '@/types/api';
import { useLayout } from '@/hooks/useLayout';

type TagFilter = 'all' | 'active' | 'blocked' | 'unassigned';
type SortKey = 'name' | 'last_scanned_at';

const DEFAULT_FILTER: TagFilter = 'all';
const DEFAULT_SORT_KEY: SortKey = 'name';
const DEFAULT_SORT_DIR = 'asc' as const;

interface RfidPageProps {
  pendingTagId?: string | null;
  onPendingTagHandled?: () => void;
}

export const RfidPage: React.FC<RfidPageProps> = ({ pendingTagId, onPendingTagHandled }) => {
  const { t } = useTranslation('rfid');
  const { showSuccess, showError } = useToast();
  const { prefs, setViewMode, setSort, setFilter } = useUserPrefs();
  // Ab Tablet-Breite ist Platz fuer Sortierung, Filter und Zeilenaktionen
  // direkt in der Leiste; nur auf dem Handy wandern sie ins Popover bzw. in
  // ein Ueberlaufmenue. Vorher lag diese Grenze bei 900px, wodurch ein
  // 834px-Tablet die volle Handy-Bedienung bekam, obwohl die Breite reicht.
  const hasInlineControls = useLayout().hasRoomForInlineControls;

  const [tags, setTags] = useState<Tag[]>([]);
  const [playlists, setPlaylists] = useState<Playlist[]>([]);
  const [tracks, setTracks] = useState<Track[]>([]);
  const [streams, setStreams] = useState<Stream[]>([]);
  const [podcasts, setPodcasts] = useState<Podcast[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');

  const sortKey = (prefs.sort['rfid']?.key ?? DEFAULT_SORT_KEY) as SortKey;
  const sortDir = prefs.sort['rfid']?.dir ?? DEFAULT_SORT_DIR;
  const viewMode = (prefs.viewMode['rfid'] ?? 'list') as 'card' | 'list';
  const tagFilter = (prefs.filter['rfid'] ?? DEFAULT_FILTER) as TagFilter;

  const filterBtnRef = useRef<HTMLButtonElement>(null);
  const [popoverOpen, setPopoverOpen] = useState(false);

  const [learnModeActive, setLearnModeActive] = useState(false);
  const [learnModeLoading, setLearnModeLoading] = useState(false);
  const [scannedTagId, setScannedTagId] = useState<string | null>(null);
  const [editTag, setEditTag] = useState<Tag | null>(null);
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [deleteTag, setDeleteTag] = useState<Tag | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [tagsData, playlistsData, tracksData, streamsData, podcastsData] = await Promise.all([
        tagsApi.getAll(),
        playlistsApi.getAll(),
        tracksApi.getAll(),
        streamsApi.getAll(),
        podcastsApi.list(),
      ]);
      setTags(tagsData);
      setPlaylists(playlistsData);
      setTracks(tracksData);
      setStreams(streamsData);
      setPodcasts(podcastsData);
    } catch {
      setError(t('toast.tag_save_error'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => { loadData(); }, [loadData]);

  const handleRfidLearning = useCallback((msg: RFIDScannedMessage) => {
    setScannedTagId(msg.data.tag_id);
    setLearnModeLoading(false);
    setEditDialogOpen(true);
    setEditTag(null);
  }, []);

  useWebSocketEvent('rfid_scanned_learning', handleRfidLearning);

  useEffect(() => {
    if (!pendingTagId) return;
    setScannedTagId(pendingTagId);
    setEditTag(null);
    setEditDialogOpen(true);
    onPendingTagHandled?.();
  }, [pendingTagId, onPendingTagHandled]);

  const handleLearnModeActivate = async () => {
    setLearnModeLoading(true);
    try {
      await tagsApi.setLearningMode(true);
      setLearnModeActive(true);
    } catch {
      setError(t('toast.tag_save_error'));
      setLearnModeLoading(false);
    }
  };

  const handleLearnModeDeactivate = async () => {
    try { await tagsApi.setLearningMode(false); } catch { /* ignore */ } finally {
      setLearnModeActive(false);
      setLearnModeLoading(false);
      setScannedTagId(null);
    }
  };

  const handleEditOpen = (tag: Tag) => {
    setEditTag(tag);
    setScannedTagId(null);
    setEditDialogOpen(true);
  };

  const handleEditSave = async (data: {
    name: string | null;
    content_type: ContentType;
    content_id: number;
    disabled: boolean;
  }) => {
    try {
      if (editTag) {
        const updated = await tagsApi.update(editTag.tag_id, data);
        setTags((prev) => prev.map((tg) => (tg.tag_id === updated.tag_id ? updated : tg)));
        showSuccess(t('toast.tag_updated'));
      } else if (scannedTagId) {
        const newTag = await tagsApi.create({ tag_id: scannedTagId, ...data });
        setTags((prev) => [...prev, newTag]);
        showSuccess(t('toast.tag_saved'));
        setLearnModeActive(false);
        await tagsApi.setLearningMode(false);
      }
    } catch {
      showError(t('toast.tag_save_error'));
    } finally {
      setEditDialogOpen(false);
      setEditTag(null);
      setScannedTagId(null);
    }
  };

  const handleToggleDisabled = async (tag: Tag) => {
    const newDisabled = !(tag.disabled ?? false);
    try {
      const updated = await tagsApi.update(tag.tag_id, { disabled: newDisabled });
      setTags((prev) => prev.map((tg) => (tg.tag_id === updated.tag_id ? updated : tg)));
      showSuccess(newDisabled ? t('toast.tag_disabled') : t('toast.tag_enabled'));
    } catch {
      showError(t('toast.tag_save_error'));
    }
  };

  const handleDeleteConfirm = async () => {
    if (!deleteTag) return;
    try {
      await tagsApi.delete(deleteTag.tag_id);
      setTags((prev) => prev.filter((tg) => tg.tag_id !== deleteTag.tag_id));
      showSuccess(t('toast.tag_deleted'));
    } catch {
      showError(t('toast.tag_delete_error'));
    } finally {
      setDeleteTag(null);
    }
  };

  const handleSortKeyChange = (_: React.MouseEvent, key: SortKey | null) => {
    if (!key) return;
    if (key === sortKey) {
      setSort('rfid', key, sortDir === 'asc' ? 'desc' : 'asc');
    } else {
      setSort('rfid', key, 'asc');
    }
  };

  const handleSortDirToggle = () => {
    setSort('rfid', sortKey, sortDir === 'asc' ? 'desc' : 'asc');
  };

  const handleViewModeChange = (_: React.MouseEvent, v: 'card' | 'list' | null) => {
    if (!v) return;
    setViewMode('rfid', v);
  };

  const handleFilterChange = (_: React.MouseEvent, val: TagFilter | null) => {
    if (val !== null) setFilter('rfid', val);
  };

  // ── Active chip helpers ───────────────────────────────────────────────────
  const hasActiveFilter = tagFilter !== DEFAULT_FILTER;
  const hasNonDefaultSort = sortKey !== DEFAULT_SORT_KEY || sortDir !== DEFAULT_SORT_DIR;
  const hasAnyActiveChip = hasActiveFilter || hasNonDefaultSort;
  const activeBadgeCount = (hasActiveFilter ? 1 : 0) + (hasNonDefaultSort ? 1 : 0);

  const filterLabel: Record<TagFilter, string> = {
    all: t('filter.all'),
    active: t('filter.active'),
    blocked: t('filter.blocked'),
    unassigned: t('filter.unassigned'),
  };
  const sortKeyLabel: Record<SortKey, string> = {
    name: t('sort.name'),
    last_scanned_at: t('sort.last_scanned'),
  };

  // ── Sort + filter controls (reused on desktop inline & in mobile popover) ─
  const filterControls = (
    <ToggleButtonGroup
      value={tagFilter}
      exclusive
      onChange={handleFilterChange}
      size="small"
      aria-label={t('filter.label')}
    >
      <ToggleButton value="all">{t('filter.all')}</ToggleButton>
      <ToggleButton value="active">{t('filter.active')}</ToggleButton>
      <ToggleButton value="blocked">{t('filter.blocked')}</ToggleButton>
      <ToggleButton value="unassigned">{t('filter.unassigned')}</ToggleButton>
    </ToggleButtonGroup>
  );

  const sortControls = (
    <Box display="flex" alignItems="center" gap={0.5}>
      <ToggleButtonGroup
        value={sortKey}
        exclusive
        onChange={handleSortKeyChange}
        size="small"
      >
        <ToggleButton value="name">{t('sort.name')}</ToggleButton>
        <ToggleButton value="last_scanned_at">{t('sort.last_scanned')}</ToggleButton>
      </ToggleButtonGroup>
      <Tooltip title={sortDir === 'asc' ? t('sort.ascending') : t('sort.descending')}>
        <IconButton size="small" onClick={handleSortDirToggle}>
          {sortDir === 'asc'
            ? <ArrowUpwardIcon fontSize="small" />
            : <ArrowDownwardIcon fontSize="small" />}
        </IconButton>
      </Tooltip>
    </Box>
  );

  // ── Filtered & sorted list ────────────────────────────────────────────────
  const filteredAndSorted = [...tags]
    .filter((tag) => {
      const q = searchQuery.toLowerCase();
      const matchesSearch =
        tag.tag_id.toLowerCase().includes(q) || (tag.name ?? '').toLowerCase().includes(q);
      if (!matchesSearch) return false;
      const isDisabled = tag.disabled ?? false;
      if (tagFilter === 'active') return !isDisabled;
      if (tagFilter === 'blocked') return isDisabled;
      if (tagFilter === 'unassigned') return !tag.content_id || tag.content_id === 0;
      return true;
    })
    .sort((a, b) => {
      let aVal: string | number;
      let bVal: string | number;
      if (sortKey === 'last_scanned_at') {
        aVal = a.last_scanned_at ? new Date(a.last_scanned_at).getTime() : 0;
        bVal = b.last_scanned_at ? new Date(b.last_scanned_at).getTime() : 0;
      } else {
        aVal = (a.name ?? a.tag_id).toLowerCase();
        bVal = (b.name ?? b.tag_id).toLowerCase();
      }
      if (aVal < bVal) return sortDir === 'asc' ? -1 : 1;
      if (aVal > bVal) return sortDir === 'asc' ? 1 : -1;
      return 0;
    });

  if (loading) return <LoadingSpinner message={t('title')} fullPage />;

  return (
    <PageShell
      title={t('title')}
      actions={
        <LearnModeButton
          active={learnModeActive}
          loading={learnModeLoading}
          onActivate={handleLearnModeActivate}
          onDeactivate={handleLearnModeDeactivate}
        />
      }
    >
      {error && <Alert severity="error" onClose={() => setError(null)} sx={{ mb: 2 }}>{error}</Alert>}

      {/* ── Toolbar ─────────────────────────────────────────────────────── */}
      <Box display="flex" gap={1} mb={1} alignItems="center" flexWrap="wrap">

        {/* View-Toggle */}
        <ToggleButtonGroup value={viewMode} exclusive onChange={handleViewModeChange} size="small">
          <ToggleButton value="card" aria-label={t('view_mode_card')}>
            <ViewModuleIcon fontSize="small" />
          </ToggleButton>
          <ToggleButton value="list" aria-label={t('view_mode_list')}>
            <ViewListIcon fontSize="small" />
          </ToggleButton>
        </ToggleButtonGroup>

        {/* Search */}
        <TextField
          placeholder={t('search_placeholder')}
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          size="small"
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon fontSize="small" />
              </InputAdornment>
            ),
          }}
          sx={{ flex: 1, minWidth: 0 }}
        />

        {/* Desktop: Filter & Sort direkt inline */}
        {hasInlineControls && (
          <>
            {filterControls}
            {sortControls}
          </>
        )}

        {/* Mobile: kompakter Icon-Button mit Badge */}
        {!hasInlineControls && (
          <Tooltip title={t('filter.open')}>
            <IconButton
              ref={filterBtnRef}
              size="small"
              onClick={() => setPopoverOpen(true)}
              aria-label={t('filter.open')}
              sx={{
                position: 'relative',
                color: activeBadgeCount > 0 ? 'primary.main' : 'text.secondary',
                border: '1px solid',
                borderColor: activeBadgeCount > 0 ? 'primary.main' : 'divider',
                borderRadius: 1,
                px: 1,
              }}
            >
              <FilterListIcon fontSize="small" />
              {activeBadgeCount > 0 && (
                <Box
                  component="span"
                  sx={{
                    position: 'absolute',
                    top: -6,
                    right: -6,
                    width: 16,
                    height: 16,
                    borderRadius: '50%',
                    bgcolor: 'primary.main',
                    color: 'primary.contrastText',
                    fontSize: '0.65rem',
                    fontWeight: 700,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  {activeBadgeCount}
                </Box>
              )}
            </IconButton>
          </Tooltip>
        )}
      </Box>

      {/* ── Active Filter Chips (beide Breakpoints, nur bei != Default) ── */}
      {hasAnyActiveChip && (
        <Box display="flex" gap={0.75} flexWrap="wrap" mb={1.5} alignItems="center">
          {hasActiveFilter && (
            <Chip
              size="small"
              label={filterLabel[tagFilter]}
              onDelete={() => setFilter('rfid', DEFAULT_FILTER)}
              color="primary"
              variant="outlined"
            />
          )}
          {hasNonDefaultSort && (
            <Chip
              size="small"
              icon={sortDir === 'asc' ? <ArrowUpwardIcon /> : <ArrowDownwardIcon />}
              label={sortKeyLabel[sortKey]}
              onDelete={() => setSort('rfid', DEFAULT_SORT_KEY, DEFAULT_SORT_DIR)}
              color="primary"
              variant="outlined"
            />
          )}
          {hasActiveFilter && hasNonDefaultSort && (
            <Chip
              size="small"
              label={t('filter.reset_all')}
              onDelete={() => {
                setFilter('rfid', DEFAULT_FILTER);
                setSort('rfid', DEFAULT_SORT_KEY, DEFAULT_SORT_DIR);
              }}
              onClick={() => {
                setFilter('rfid', DEFAULT_FILTER);
                setSort('rfid', DEFAULT_SORT_KEY, DEFAULT_SORT_DIR);
              }}
              variant="outlined"
              sx={{ borderColor: 'divider', color: 'text.secondary' }}
            />
          )}
        </Box>
      )}

      {/* ── Mobile Popover ───────────────────────────────────────────────── */}
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
              {t('filter.label')}
            </Typography>
            <ToggleButtonGroup
              value={tagFilter}
              exclusive
              onChange={handleFilterChange}
              size="small"
              fullWidth
              sx={{ '& .MuiToggleButton-root': { flex: 1, fontSize: '0.78rem' } }}
            >
              <ToggleButton value="all">{t('filter.all')}</ToggleButton>
              <ToggleButton value="active">{t('filter.active')}</ToggleButton>
              <ToggleButton value="blocked">{t('filter.blocked')}</ToggleButton>
              <ToggleButton value="unassigned">{t('filter.unassigned')}</ToggleButton>
            </ToggleButtonGroup>
          </Box>

          <Divider />

          <Box>
            <Typography variant="caption" color="text.secondary" fontWeight={600} display="block" mb={0.75}>
              {t('sort.label')}
            </Typography>
            <Box display="flex" gap={1} alignItems="center">
              <ToggleButtonGroup
                value={sortKey}
                exclusive
                onChange={handleSortKeyChange}
                size="small"
                sx={{ flex: 1, '& .MuiToggleButton-root': { flex: 1, fontSize: '0.78rem' } }}
              >
                <ToggleButton value="name">{t('sort.name')}</ToggleButton>
                <ToggleButton value="last_scanned_at">{t('sort.last_scanned')}</ToggleButton>
              </ToggleButtonGroup>
              <Tooltip title={sortDir === 'asc' ? t('sort.ascending') : t('sort.descending')}>
                <IconButton size="small" onClick={handleSortDirToggle}>
                  {sortDir === 'asc'
                    ? <ArrowUpwardIcon fontSize="small" />
                    : <ArrowDownwardIcon fontSize="small" />}
                </IconButton>
              </Tooltip>
            </Box>
          </Box>

          {hasAnyActiveChip && (
            <>
              <Divider />
              <Box
                component="button"
                onClick={() => {
                  setFilter('rfid', DEFAULT_FILTER);
                  setSort('rfid', DEFAULT_SORT_KEY, DEFAULT_SORT_DIR);
                  setPopoverOpen(false);
                }}
                sx={{
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  color: 'text.secondary',
                  fontSize: '0.8rem',
                  textAlign: 'left',
                  p: 0,
                  '&:hover': { color: 'text.primary' },
                }}
              >
                {t('filter.reset_all')}
              </Box>
            </>
          )}
        </Paper>
      </Popover>

      <TagList
        tags={filteredAndSorted}
        playlists={playlists}
        tracks={tracks}
        streams={streams}
        podcasts={podcasts}
        viewMode={viewMode}
        onEdit={handleEditOpen}
        onDelete={setDeleteTag}
        onToggleDisabled={handleToggleDisabled}
      />

      <TagEditDialog
        open={editDialogOpen}
        tag={editTag}
        newTagId={scannedTagId}
        playlists={playlists}
        tracks={tracks}
        streams={streams}
        podcasts={podcasts}
        onSave={handleEditSave}
        onClose={() => {
          if (learnModeActive) {
            tagsApi.setLearningMode(false).catch(() => {});
            setLearnModeActive(false);
            setLearnModeLoading(false);
          }
          setEditDialogOpen(false);
          setEditTag(null);
          setScannedTagId(null);
        }}
      />

      <Dialog open={!!deleteTag} onClose={() => setDeleteTag(null)}>
        <DialogTitle>{t('delete_tag')}</DialogTitle>
        <DialogContent>
          <DialogContentText>
            {t('delete_confirm', { name: deleteTag?.name ?? deleteTag?.tag_id })}
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <ActionButton actionType="secondary" onClick={() => setDeleteTag(null)}>
            {t('cancel', { ns: 'common' })}
          </ActionButton>
          <ActionButton actionType="destructive" onClick={handleDeleteConfirm}>
            {t('delete', { ns: 'common' })}
          </ActionButton>
        </DialogActions>
      </Dialog>
    </PageShell>
  );
};
