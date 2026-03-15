import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  IconButton,
  InputAdornment,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Tooltip,
} from '@mui/material';
import ArrowDownwardIcon from '@mui/icons-material/ArrowDownward';
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward';
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

type DisabledFilter = 'all' | 'active' | 'blocked';
type SortKey = 'name' | 'last_scanned_at';

interface RfidPageProps {
  pendingTagId?: string | null;
  onPendingTagHandled?: () => void;
}

export const RfidPage: React.FC<RfidPageProps> = ({ pendingTagId, onPendingTagHandled }) => {
  const { t } = useTranslation('rfid');
  const { showSuccess, showError } = useToast();
  const { prefs, setViewMode, setSort, setFilter } = useUserPrefs();

  const [tags, setTags] = useState<Tag[]>([]);
  const [playlists, setPlaylists] = useState<Playlist[]>([]);
  const [tracks, setTracks] = useState<Track[]>([]);
  const [streams, setStreams] = useState<Stream[]>([]);
  const [podcasts, setPodcasts] = useState<Podcast[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');

  // #81 — all view state read from persistent prefs
  const sortKey = (prefs.sort['rfid']?.key ?? 'name') as SortKey;
  const sortDir = prefs.sort['rfid']?.dir ?? 'asc';
  const viewMode = (prefs.viewMode['rfid'] ?? 'list') as 'card' | 'list';
  const disabledFilter = (prefs.filter['rfid'] ?? 'all') as DisabledFilter;

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

  // #81 — all changes go directly into prefs (no local state needed)
  const handleSortKey = (_: React.MouseEvent, key: SortKey | null) => {
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

  const handleDisabledFilterChange = (_: React.MouseEvent, val: DisabledFilter | null) => {
    if (val !== null) setFilter('rfid', val);
  };

  const filteredAndSorted = [...tags]
    .filter((tag) => {
      const q = searchQuery.toLowerCase();
      const matchesSearch =
        tag.tag_id.toLowerCase().includes(q) || (tag.name ?? '').toLowerCase().includes(q);
      if (!matchesSearch) return false;
      const isDisabled = tag.disabled ?? false;
      if (disabledFilter === 'active') return !isDisabled;
      if (disabledFilter === 'blocked') return isDisabled;
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

      <Box display="flex" gap={2} mb={2} flexWrap="wrap" alignItems="center">
        <ToggleButtonGroup value={viewMode} exclusive onChange={handleViewModeChange} size="small">
          <ToggleButton value="card" aria-label={t('view_mode_card', { defaultValue: 'Kachelansicht' })}>
            <ViewModuleIcon />
          </ToggleButton>
          <ToggleButton value="list" aria-label={t('view_mode_list', { defaultValue: 'Listenansicht' })}>
            <ViewListIcon />
          </ToggleButton>
        </ToggleButtonGroup>

        <TextField
          placeholder={t('search_placeholder')}
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          size="small"
          InputProps={{
            startAdornment: <InputAdornment position="start"><SearchIcon /></InputAdornment>,
          }}
          sx={{ minWidth: 200 }}
        />

        <ToggleButtonGroup
          value={disabledFilter}
          exclusive
          onChange={handleDisabledFilterChange}
          size="small"
          aria-label={t('filter.label')}
        >
          <ToggleButton value="all">{t('filter.all')}</ToggleButton>
          <ToggleButton value="active">{t('filter.active')}</ToggleButton>
          <ToggleButton value="blocked">{t('filter.blocked')}</ToggleButton>
        </ToggleButtonGroup>

        <Box display="flex" alignItems="center" gap={0.5} ml="auto">
          <ToggleButtonGroup value={sortKey} exclusive onChange={handleSortKey} size="small">
            <ToggleButton value="name">{t('sort.name', { defaultValue: 'Name' })}</ToggleButton>
            <ToggleButton value="last_scanned_at">{t('sort.last_scanned', { defaultValue: 'Zuletzt gespielt' })}</ToggleButton>
          </ToggleButtonGroup>
          <Tooltip title={sortDir === 'asc' ? t('sort.ascending', { defaultValue: 'Aufsteigend' }) : t('sort.descending', { defaultValue: 'Absteigend' })}>
            <IconButton size="small" onClick={handleSortDirToggle}>
              {sortDir === 'asc' ? <ArrowUpwardIcon fontSize="small" /> : <ArrowDownwardIcon fontSize="small" />}
            </IconButton>
          </Tooltip>
        </Box>
      </Box>

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
