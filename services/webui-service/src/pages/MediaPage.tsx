import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Alert,
  Box,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  Stack,
  TextField,
} from '@mui/material';
import HistoryIcon from '@mui/icons-material/History';
import MicNoneIcon from '@mui/icons-material/MicNone';
import MusicNoteIcon from '@mui/icons-material/MusicNote';
import QueueMusicIcon from '@mui/icons-material/QueueMusic';
import RadioIcon from '@mui/icons-material/Radio';
import { useTranslation } from 'react-i18next';
import { ActionButton } from '@/components/ui/ActionButton';
import { CoverUploadField } from '@/components/media/CoverUploadField';
import { MediaFab, type MediaTab } from '@/components/media/MediaFab';
import { MediaImportDialog } from '@/components/media/MediaImportDialog';
import { MediaOverviewTab } from '@/components/media/MediaOverviewTab';
import { PlaylistList } from '@/components/media/PlaylistList';
import { RemoteTrackDialog } from '@/components/media/RemoteTrackDialog';
import { PodcastDialog } from '@/components/media/PodcastDialog';
import { PodcastList } from '@/components/media/PodcastList';
import { StreamDialog } from '@/components/media/StreamDialog';
import { StreamList } from '@/components/media/StreamList';
import { TrackList } from '@/components/media/TrackList';
import { RecordDialog } from '@/components/media/RecordDialog';
import { UploadDialog } from '@/components/media/UploadDialog';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { PageShell } from '@/components/common/PageShell';
import { SectionTabs } from '@/components/common/SectionTabs';
import { useToast } from '@/contexts/ToastContext';
import { useUserPrefs } from '@/contexts/UserPrefsContext';
import { useFeatureInstalled } from '@/contexts/CapabilitiesContext';
import { playlistsApi } from '@/api/playlists';
import { podcastFoldersApi, podcastsApi } from '@/api/podcasts';
import { streamFoldersApi, streamsApi } from '@/api/streams';
import { trackFoldersApi, tracksApi } from '@/api/tracks';
import { tagsApi } from '@/api/tags';
import type {
  Playlist,
  Podcast,
  PodcastFolder,
  Stream,
  StreamFolder,
  Track,
  TrackFolder,
} from '@/types/api';
import { ResponsiveDialog } from '@/components/common/ResponsiveDialog';
import { useMediaFolderActions } from '@/hooks/useMediaFolderActions';
import { useObjectUrl } from '@/hooks/useObjectUrl';
import { TabPanel } from '@/components/common/TabPanel';

/** The three media types the delete dialog works on. */
type MediaKind = 'track' | 'stream' | 'podcast';

/** Tab order of the page - the index in the state, the name for the FAB. */
const TAB_ORDER: readonly MediaTab[] = ['overview', 'playlists', 'tracks', 'streams', 'podcasts'];

interface DeleteTarget {
  type: MediaKind;
  item: { id: number };
}

export const MediaPage: React.FC = () => {
  const { t } = useTranslation('media');
  const { showSuccess, showError } = useToast();
  const { prefs, setViewMode, setSort, setFilter, setTreeCollapsed, setPageSize } = useUserPrefs();
  const [tab, setTab] = useState(0);
  const [playlists, setPlaylists] = useState<Playlist[]>([]);
  const [tracks, setTracks] = useState<Track[]>([]);
  const [folders, setFolders] = useState<TrackFolder[]>([]);
  const [currentFolderId, setCurrentFolderId] = useState<number | null>(null);
  const [streams, setStreams] = useState<Stream[]>([]);
  const [streamFolders, setStreamFolders] = useState<StreamFolder[]>([]);
  const [currentStreamFolderId, setCurrentStreamFolderId] = useState<number | null>(null);
  const [podcasts, setPodcasts] = useState<Podcast[]>([]);
  const [podcastFolders, setPodcastFolders] = useState<PodcastFolder[]>([]);
  const [currentPodcastFolderId, setCurrentPodcastFolderId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [recordOpen, setRecordOpen] = useState(false);
  const [remoteTrackOpen, setRemoteTrackOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const mediaDownloaderInstalled = useFeatureInstalled('media_downloader');
  const [streamOpen, setStreamOpen] = useState(false);
  const [podcastOpen, setPodcastOpen] = useState(false);

  // Which folder a new track lands in. Only the tracks tab shows a tree, so
  // only there does "the current folder" mean anything: from the overview the
  // FAB creates in the root, rather than in a folder the page is not showing.
  const uploadTargetFolderId = TAB_ORDER[tab] === 'tracks' ? currentFolderId : null;
  const [playlistCreateOpen, setPlaylistCreateOpen] = useState(false);

  const createTrackFolderRef = useRef<(() => void) | null>(null);
  const createStreamFolderRef = useRef<(() => void) | null>(null);
  const createPodcastFolderRef = useRef<(() => void) | null>(null);

  const [editTrack, setEditTrack] = useState<Track | null>(null);
  const [editForm, setEditForm] = useState({ title: '', artist: '', album: '' });
  const [editCoverFile, setEditCoverFile] = useState<File | null>(null);
  const editCoverPreview = useObjectUrl(editCoverFile);
  const [editSaving, setEditSaving] = useState(false);

  const [deleteTarget, setDeleteTarget] = useState<DeleteTarget | null>(null);
  const [assignedTagNames, setAssignedTagNames] = useState<string[]>([]);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [
        playlistsData,
        tracksData,
        streamsData,
        podcastsData,
        foldersData,
        streamFoldersData,
        podcastFoldersData,
      ] = await Promise.all([
        playlistsApi.getAll(),
        tracksApi.getAll(),
        streamsApi.getAll(),
        podcastsApi.list(),
        trackFoldersApi.getAll(),
        streamFoldersApi.getAll(),
        podcastFoldersApi.getAll(),
      ]);
      setPlaylists(playlistsData);
      setTracks(tracksData);
      setStreams(streamsData);
      setPodcasts(podcastsData);
      setFolders(foldersData);
      setStreamFolders(streamFoldersData);
      setPodcastFolders(podcastFoldersData);
    } catch {
      setError(t('tracks.load_error'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => { loadData(); }, [loadData]);

  const handlePlaylistUpdated = (updated: Playlist) => {
    setPlaylists((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
  };

  const trackFolderActions = useMediaFolderActions({
    foldersApi: trackFoldersApi,
    setFolders,
    setItems: setTracks,
    reloadItems: () => tracksApi.getAll(),
    moveItem: (id, folderId) => tracksApi.update(id, { folder_id: folderId }),
    movedMessage: t('folders.track_moved'),
    moveErrorMessage: t('folders.move_error'),
  });

  const streamFolderActions = useMediaFolderActions({
    foldersApi: streamFoldersApi,
    setFolders: setStreamFolders,
    setItems: setStreams,
    reloadItems: () => streamsApi.getAll(),
    moveItem: (id, folderId) => streamsApi.update(id, { folder_id: folderId }),
    movedMessage: t('folders.stream_moved'),
    moveErrorMessage: t('folders.stream_move_error'),
  });

  const podcastFolderActions = useMediaFolderActions({
    foldersApi: podcastFoldersApi,
    setFolders: setPodcastFolders,
    setItems: setPodcasts,
    reloadItems: () => podcastsApi.list(),
    moveItem: (id, folderId) => podcastsApi.update(id, { folder_id: folderId }),
    movedMessage: t('folders.podcast_moved'),
    moveErrorMessage: t('folders.podcast_move_error'),
  });

  const checkAndConfirmDelete = async (target: DeleteTarget) => {
    try {
      const allTags = await tagsApi.getAll();
      const affected = allTags.filter(
        (tag) => tag.content_type === target.type && tag.content_id === target.item.id
      );
      setAssignedTagNames(affected.map((tg) => tg.name ?? tg.tag_id));
    } catch {
      setAssignedTagNames([]);
    }
    setDeleteTarget(target);
    setDeleteDialogOpen(true);
  };

  const closeDeleteDialog = () => {
    setDeleteDialogOpen(false);
    setDeleteTarget(null);
    setAssignedTagNames([]);
  };

  /** How each media type is deleted, and what to say about it afterwards. */
  const deleteByKind: Record<MediaKind, {
    remove: (id: number) => Promise<void>;
    success: string;
    error: string;
  }> = {
    track: {
      remove: async (id) => {
        await tracksApi.delete(id);
        setTracks((prev) => prev.filter((tr) => tr.id !== id));
      },
      success: t('tracks.deleted'),
      error: t('tracks.delete_error'),
    },
    stream: {
      remove: async (id) => {
        await streamsApi.delete(id);
        setStreams((prev) => prev.filter((s) => s.id !== id));
      },
      success: t('tracks.stream_deleted'),
      error: t('streams.delete_error'),
    },
    podcast: {
      remove: async (id) => {
        await podcastsApi.delete(id);
        setPodcasts((prev) => prev.filter((p) => p.id !== id));
      },
      success: t('podcasts.deleted'),
      error: t('podcasts.delete_error'),
    },
  };

  const performDelete = async (unassignTags: boolean) => {
    if (!deleteTarget) return;
    if (unassignTags && assignedTagNames.length > 0) {
      try {
        const allTags = await tagsApi.getAll();
        const affected = allTags.filter(
          (tag) => tag.content_type === deleteTarget.type && tag.content_id === deleteTarget.item.id
        );
        await Promise.all(
          affected.map((tag) =>
            tagsApi.update(tag.tag_id, {
              // Both, not just content_id: the backend clears exactly the
              // fields it finds as an explicit null, and a tag left with a
              // content_type but no content_id still claims to point at a
              // track that no longer exists.
              content_type: null,
              content_id: null,
              name: tag.name ?? null,
              disabled: tag.disabled ?? false,
            })
          )
        );
      } catch { /* ignore */ }
    }
    const { remove, success, error: errorMessage } = deleteByKind[deleteTarget.type];
    try {
      await remove(deleteTarget.item.id);
      showSuccess(success);
    } catch {
      showError(errorMessage);
    } finally {
      closeDeleteDialog();
    }
  };

  const handleTrackEdit = (track: Track) => {
    setEditTrack(track);
    setEditForm({ title: track.title, artist: track.artist ?? '', album: track.album ?? '' });
    setEditCoverFile(null);
  };

  const handleTrackEditSave = async () => {
    if (!editTrack) return;
    setEditSaving(true);
    try {
      let updated = await tracksApi.update(editTrack.id, {
        title: editForm.title.trim() || editTrack.title,
        artist: editForm.artist.trim() || null,
        album: editForm.album.trim() || null,
      });
      if (editCoverFile) updated = await tracksApi.uploadCover(editTrack.id, editCoverFile);
      setTracks((prev) => prev.map((tr) => (tr.id === updated.id ? updated : tr)));
      setEditTrack(null);
      setEditCoverFile(null);
      showSuccess(t('tracks.updated'));
    } catch {
      showError(t('tracks.update_error'));
    } finally {
      setEditSaving(false);
    }
  };

  const handleTrackEditRemoveCover = () => {
    if (editCoverFile) { setEditCoverFile(null); return; }
    if (editTrack?.cover_art_url) {
      tracksApi.deleteCover(editTrack.id)
        .then((updated) => {
          setTracks((prev) => prev.map((tr) => (tr.id === updated.id ? updated : tr)));
          setEditTrack(updated);
        })
        .catch(() => showError(t('tracks.update_error')));
    }
  };

  const getSort = (scope: string) => prefs.sort[scope] ?? { key: 'title', dir: 'asc' as const };
  const getViewMode = (scope: string) => prefs.viewMode[scope] ?? 'list';
  const getFilter = (scope: string) => prefs.filter[scope] ?? 'all';

  if (loading) return <LoadingSpinner message={t('title')} fullPage />;

  return (
    <PageShell title={t('title')}>
      {error && (
        <Alert severity="error" onClose={() => setError(null)} sx={{ mb: 2 }}>{error}</Alert>
      )}

      <SectionTabs
        value={tab}
        onChange={setTab}
        ariaLabel={t('navigation.media', { ns: 'common' })}
        sections={[
          { label: t('tabs.recent'), icon: <HistoryIcon /> },
          { label: t('tabs.playlists'), icon: <QueueMusicIcon />, count: playlists.length },
          { label: t('tabs.tracks'), icon: <MusicNoteIcon />, count: tracks.length },
          { label: t('tabs.streams'), icon: <RadioIcon />, count: streams.length },
          { label: t('tabs.podcasts'), icon: <MicNoneIcon />, count: podcasts.length },
        ]}
      />

      <TabPanel value={tab} index={0}>
        <MediaOverviewTab
          tracks={tracks}
          playlists={playlists}
          streams={streams}
          podcasts={podcasts}
          onNavigateTab={(targetTab) => setTab(targetTab)}
        />
      </TabPanel>

      <TabPanel value={tab} index={1}>
        <PlaylistList
          playlists={playlists}
          tracks={tracks}
          onUpdate={(pl) => setPlaylists((prev) => prev.map((p) => (p.id === pl.id ? pl : p)))}
          onDelete={(pl) => setPlaylists((prev) => prev.filter((p) => p.id !== pl.id))}
          onCreate={(pl) => setPlaylists((prev) => [...prev, pl])}
          viewMode={getViewMode('playlists') as 'card' | 'list'}
          onViewModeChange={(mode) => setViewMode('playlists', mode)}
          sortKey={getSort('playlists').key}
          sortDir={getSort('playlists').dir}
          onSortChange={(key, dir) => setSort('playlists', key, dir)}
          createOpen={playlistCreateOpen}
          onCreateOpenHandled={() => setPlaylistCreateOpen(false)}
        />
      </TabPanel>

      <TabPanel value={tab} index={2}>
        <TrackList
          tracks={tracks}
          folders={folders}
          playlists={playlists}
          currentFolderId={currentFolderId}
          onNavigateFolder={setCurrentFolderId}
          onFolderCreate={trackFolderActions.create}
          onFolderRename={trackFolderActions.rename}
          onFolderDelete={trackFolderActions.remove}
          onMoveTrackToFolder={trackFolderActions.move}
          onDelete={(track) => void checkAndConfirmDelete({ type: 'track', item: track })}
          onEdit={handleTrackEdit}
          sortKey={getSort('tracks').key}
          sortDir={getSort('tracks').dir}
          onSortChange={(key, dir) => setSort('tracks', key, dir)}
          viewMode={getViewMode('tracks')}
          onViewModeChange={(mode) => setViewMode('tracks', mode)}
          filter={getFilter('tracks')}
          onFilterChange={(val) => setFilter('tracks', val)}
          treeCollapsed={prefs.treeCollapsed.tracks ?? false}
          onTreeCollapsedChange={(collapsed) => setTreeCollapsed('tracks', collapsed)}
          pageSize={prefs.pageSize.tracks ?? 25}
          onPageSizeChange={(size) => setPageSize('tracks', size)}
          onRegisterCreateFolder={(fn) => { createTrackFolderRef.current = fn; }}
          onPlaylistUpdated={handlePlaylistUpdated}
        />
      </TabPanel>

      <TabPanel value={tab} index={3}>
        <StreamList
          streams={streams}
          folders={streamFolders}
          currentFolderId={currentStreamFolderId}
          onNavigateFolder={setCurrentStreamFolderId}
          onFolderCreate={streamFolderActions.create}
          onFolderRename={streamFolderActions.rename}
          onFolderDelete={streamFolderActions.remove}
          onMoveStreamToFolder={streamFolderActions.move}
          onDelete={(stream) => void checkAndConfirmDelete({ type: 'stream', item: stream })}
          onUpdate={(s) => setStreams((prev) => prev.map((x) => (x.id === s.id ? s : x)))}
          sortKey={getSort('streams').key}
          sortDir={getSort('streams').dir}
          onSortChange={(key, dir) => setSort('streams', key, dir)}
          viewMode={getViewMode('streams')}
          onViewModeChange={(mode) => setViewMode('streams', mode)}
          treeCollapsed={prefs.treeCollapsed.streams ?? false}
          onTreeCollapsedChange={(collapsed) => setTreeCollapsed('streams', collapsed)}
          pageSize={prefs.pageSize.streams ?? 25}
          onPageSizeChange={(size) => setPageSize('streams', size)}
          onRegisterCreateFolder={(fn) => { createStreamFolderRef.current = fn; }}
        />
      </TabPanel>

      <TabPanel value={tab} index={4}>
        <PodcastList
          podcasts={podcasts}
          folders={podcastFolders}
          currentFolderId={currentPodcastFolderId}
          onNavigateFolder={setCurrentPodcastFolderId}
          onFolderCreate={podcastFolderActions.create}
          onFolderRename={podcastFolderActions.rename}
          onFolderDelete={podcastFolderActions.remove}
          onMovePodcastToFolder={podcastFolderActions.move}
          onDelete={(podcast) => void checkAndConfirmDelete({ type: 'podcast', item: podcast })}
          onUpdate={(p) => setPodcasts((prev) => prev.map((x) => (x.id === p.id ? p : x)))}
          sortKey={getSort('podcasts').key}
          sortDir={getSort('podcasts').dir}
          onSortChange={(key, dir) => setSort('podcasts', key, dir)}
          viewMode={getViewMode('podcasts')}
          onViewModeChange={(mode) => setViewMode('podcasts', mode)}
          treeCollapsed={prefs.treeCollapsed.podcasts ?? false}
          onTreeCollapsedChange={(collapsed) => setTreeCollapsed('podcasts', collapsed)}
          pageSize={prefs.pageSize.podcasts ?? 25}
          onPageSizeChange={(size) => setPageSize('podcasts', size)}
          onRegisterCreateFolder={(fn) => { createPodcastFolderRef.current = fn; }}
        />
      </TabPanel>

      <MediaFab
        tab={TAB_ORDER[tab]}
        onCreatePlaylist={() => setPlaylistCreateOpen(true)}
        onCreateFolder={() => createTrackFolderRef.current?.()}
        onUpload={() => setUploadOpen(true)}
        onRecord={() => setRecordOpen(true)}
        onRemoteTrack={() => setRemoteTrackOpen(true)}
        onImport={() => setImportOpen(true)}
        onCreateStream={() => setStreamOpen(true)}
        onCreateStreamFolder={() => createStreamFolderRef.current?.()}
        onCreatePodcast={() => setPodcastOpen(true)}
        onCreatePodcastFolder={() => createPodcastFolderRef.current?.()}
      />

      <Dialog open={deleteDialogOpen} onClose={closeDeleteDialog} maxWidth="xs" fullWidth>
        <DialogTitle>{t('media.delete_confirm_title')}</DialogTitle>
        <DialogContent>
          {assignedTagNames.length > 0 ? (
            <DialogContentText>
              {t('media.delete_assigned_warning')}
              <Box component="ul" sx={{ mt: 1, pl: 2 }}>
                {assignedTagNames.map((name) => <li key={name}>{name}</li>)}
              </Box>
            </DialogContentText>
          ) : (
            <DialogContentText>
              {t('media.delete_confirm_text')}
            </DialogContentText>
          )}
        </DialogContent>
        <DialogActions>
          <Stack direction={assignedTagNames.length > 0 ? 'column' : 'row'} spacing={1} sx={{ width: '100%', px: 1, pb: 1 }}>
            <ActionButton actionType="secondary" onClick={closeDeleteDialog} fullWidth>
              {t('cancel', { ns: 'common' })}
            </ActionButton>
            {assignedTagNames.length > 0 && (
              <ActionButton actionType="destructive" onClick={() => void performDelete(false)} fullWidth>
                {t('media.delete_media_only')}
              </ActionButton>
            )}
            <ActionButton actionType="destructive" onClick={() => void performDelete(assignedTagNames.length > 0)} fullWidth>
              {assignedTagNames.length > 0
                ? t('media.delete_media_and_unassign')
                : t('delete', { ns: 'common' })}
            </ActionButton>
          </Stack>
        </DialogActions>
      </Dialog>

      <ResponsiveDialog open={!!editTrack} onClose={() => { setEditTrack(null); setEditCoverFile(null); }} maxWidth="sm" fullWidth>
        <DialogTitle>{t('tracks.edit')}</DialogTitle>
        <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: '16px !important' }}>
          <CoverUploadField
            displayUrl={editCoverPreview ?? editTrack?.cover_art_url ?? null}
            coverFile={editCoverFile}
            onFileSelect={(file) => setEditCoverFile(file)}
            onRemove={handleTrackEditRemoveCover}
          />
          <TextField label={t('tracks.fields.title')} value={editForm.title}
            onChange={(e) => setEditForm((p) => ({ ...p, title: e.target.value }))}
            size="small" fullWidth required />
          <TextField label={t('tracks.fields.artist')} value={editForm.artist}
            onChange={(e) => setEditForm((p) => ({ ...p, artist: e.target.value }))}
            size="small" fullWidth />
          <TextField label={t('tracks.fields.album')} value={editForm.album}
            onChange={(e) => setEditForm((p) => ({ ...p, album: e.target.value }))}
            size="small" fullWidth />
        </DialogContent>
        <DialogActions>
          <ActionButton actionType="secondary" onClick={() => setEditTrack(null)}>{t('cancel', { ns: 'common' })}</ActionButton>
          <ActionButton actionType="primary" loading={editSaving} disabled={editSaving || !editForm.title.trim()} onClick={handleTrackEditSave}>
            {t('save', { ns: 'common' })}
          </ActionButton>
        </DialogActions>
      </ResponsiveDialog>

      <UploadDialog
        open={uploadOpen}
        onClose={() => setUploadOpen(false)}
        currentFolderId={uploadTargetFolderId}
        onSuccess={(track) => { setTracks((prev) => [...prev, track]); setUploadOpen(false); showSuccess(t('tracks.uploaded')); }}
      />
      <RecordDialog
        open={recordOpen}
        onClose={() => setRecordOpen(false)}
        currentFolderId={uploadTargetFolderId}
        onSuccess={(track) => { setTracks((prev) => [...prev, track]); setRecordOpen(false); showSuccess(t('tracks.recorded')); }}
      />
      <RemoteTrackDialog open={remoteTrackOpen} onClose={() => setRemoteTrackOpen(false)}
        onSuccess={(track) => { setTracks((prev) => [...prev, track]); setRemoteTrackOpen(false); showSuccess(t('tracks.remote_added')); }} />
      {mediaDownloaderInstalled && (
        <MediaImportDialog
          open={importOpen}
          onClose={() => setImportOpen(false)}
          onSuccess={(track) => {
            setTracks((prev) => [...prev, track]);
            setImportOpen(false);
            showSuccess(t('tracks.imported'));
          }}
        />
      )}
      <StreamDialog open={streamOpen} onClose={() => setStreamOpen(false)}
        onSuccess={(stream) => { setStreams((prev) => [...prev, stream]); setStreamOpen(false); showSuccess(t('tracks.stream_added')); }} />
      <PodcastDialog open={podcastOpen} onClose={() => setPodcastOpen(false)}
        onSuccess={(podcast) => { setPodcasts((prev) => [...prev, podcast]); setPodcastOpen(false); showSuccess(t('podcasts.created')); }} />
    </PageShell>
  );
};
