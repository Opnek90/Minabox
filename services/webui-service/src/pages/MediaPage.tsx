import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  Stack,
  Tab,
  Tabs,
  TextField,
} from '@mui/material';
import CloudUploadIcon from '@mui/icons-material/CloudUpload';
import LinkIcon from '@mui/icons-material/Link';
import PlaylistAddIcon from '@mui/icons-material/PlaylistAdd';
import PodcastsIcon from '@mui/icons-material/Podcasts';
import StreamIcon from '@mui/icons-material/Stream';
import { useTranslation } from 'react-i18next';
import { ActionButton } from '@/components/ui/ActionButton';
import { CoverUploadField } from '@/components/media/CoverUploadField';
import { PlaylistList } from '@/components/media/PlaylistList';
import { RemoteTrackDialog } from '@/components/media/RemoteTrackDialog';
import { PodcastDialog } from '@/components/media/PodcastDialog';
import { PodcastList } from '@/components/media/PodcastList';
import { StreamDialog } from '@/components/media/StreamDialog';
import { StreamList } from '@/components/media/StreamList';
import { TrackList } from '@/components/media/TrackList';
import { UploadDialog } from '@/components/media/UploadDialog';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { PageShell } from '@/components/common/PageShell';
import { useToast } from '@/contexts/ToastContext';
import { useUserPrefs } from '@/contexts/UserPrefsContext';
import { playlistsApi } from '@/api/playlists';
import { podcastsApi } from '@/api/podcasts';
import { streamsApi } from '@/api/streams';
import { tracksApi } from '@/api/tracks';
import { tagsApi } from '@/api/tags';
import type { Playlist, Podcast, Stream, Track } from '@/types/api';

interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}

const TabPanel: React.FC<TabPanelProps> = ({ children, value, index }) => (
  <Box role="tabpanel" hidden={value !== index} sx={{ pt: 2 }}>
    {value === index && children}
  </Box>
);

type DeleteTarget =
  | { type: 'track'; item: Track }
  | { type: 'stream'; item: Stream }
  | { type: 'podcast'; item: Podcast };

export const MediaPage: React.FC = () => {
  const { t } = useTranslation('media');
  const { showSuccess, showError } = useToast();
  const { prefs, setViewMode, setSort, setFilter } = useUserPrefs();
  const [tab, setTab] = useState(0);
  const [playlists, setPlaylists] = useState<Playlist[]>([]);
  const [tracks, setTracks] = useState<Track[]>([]);
  const [streams, setStreams] = useState<Stream[]>([]);
  const [podcasts, setPodcasts] = useState<Podcast[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [remoteTrackOpen, setRemoteTrackOpen] = useState(false);
  const [streamOpen, setStreamOpen] = useState(false);
  const [podcastOpen, setPodcastOpen] = useState(false);

  // Signal an PlaylistList: Create-Dialog öffnen
  const [playlistCreateOpen, setPlaylistCreateOpen] = useState(false);

  const [editTrack, setEditTrack] = useState<Track | null>(null);
  const [editForm, setEditForm] = useState({ title: '', artist: '', album: '' });
  const [editCoverFile, setEditCoverFile] = useState<File | null>(null);
  const [editSaving, setEditSaving] = useState(false);

  const [deleteTarget, setDeleteTarget] = useState<DeleteTarget | null>(null);
  const [assignedTagNames, setAssignedTagNames] = useState<string[]>([]);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [playlistsData, tracksData, streamsData, podcastsData] = await Promise.all([
        playlistsApi.getAll(),
        tracksApi.getAll(),
        streamsApi.getAll(),
        podcastsApi.list(),
      ]);
      setPlaylists(playlistsData);
      setTracks(tracksData);
      setStreams(streamsData);
      setPodcasts(podcastsData);
    } catch {
      setError(t('tracks.load_error'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => { loadData(); }, [loadData]);

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
              content_id: null,
              name: tag.name ?? null,
              disabled: tag.disabled ?? false,
            })
          )
        );
      } catch { /* ignore */ }
    }
    try {
      if (deleteTarget.type === 'track') {
        await tracksApi.delete(deleteTarget.item.id);
        setTracks((prev) => prev.filter((tr) => tr.id !== deleteTarget.item.id));
        showSuccess(t('tracks.deleted'));
      } else if (deleteTarget.type === 'stream') {
        await streamsApi.delete(deleteTarget.item.id);
        setStreams((prev) => prev.filter((s) => s.id !== deleteTarget.item.id));
        showSuccess(t('streams.deleted'));
      } else {
        await podcastsApi.delete(deleteTarget.item.id);
        setPodcasts((prev) => prev.filter((p) => p.id !== deleteTarget.item.id));
        showSuccess(t('podcasts.deleted'));
      }
    } catch {
      showError(
        deleteTarget.type === 'track'
          ? t('tracks.delete_error')
          : deleteTarget.type === 'stream'
          ? t('streams.delete_error')
          : t('podcasts.delete_error')
      );
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
    <PageShell
      title={t('title')}
      actions={
        tab === 0 ? (
          <ActionButton
            actionType="primary"
            startIcon={<PlaylistAddIcon />}
            onClick={() => setPlaylistCreateOpen(true)}
          >
            {t('playlists.add_playlist')}
          </ActionButton>
        ) : tab === 1 ? (
          <>
            <ActionButton actionType="secondary" startIcon={<LinkIcon />} onClick={() => setRemoteTrackOpen(true)}>
              {t('tracks.add_remote', { defaultValue: 'Remote-Track' })}
            </ActionButton>
            <ActionButton actionType="primary" startIcon={<CloudUploadIcon />} onClick={() => setUploadOpen(true)}>
              {t('tracks.upload')}
            </ActionButton>
          </>
        ) : tab === 2 ? (
          <ActionButton actionType="primary" startIcon={<StreamIcon />} onClick={() => setStreamOpen(true)}>
            {t('tracks.add_stream')}
          </ActionButton>
        ) : tab === 3 ? (
          <ActionButton actionType="primary" startIcon={<PodcastsIcon />} onClick={() => setPodcastOpen(true)}>
            {t('podcasts.add')}
          </ActionButton>
        ) : undefined
      }
    >
      {error && (
        <Alert severity="error" onClose={() => setError(null)} sx={{ mb: 2 }}>{error}</Alert>
      )}

      <Tabs
        value={tab}
        onChange={(_, v) => setTab(v)}
        variant="scrollable"
        scrollButtons="auto"
        allowScrollButtonsMobile
        sx={{ borderBottom: 1, borderColor: 'divider' }}
      >
        <Tab label={t('tabs.playlists')} />
        <Tab label={t('tabs.tracks')} />
        <Tab label={t('tabs.streams', { defaultValue: 'Streams' })} />
        <Tab label={t('tabs.podcasts')} />
      </Tabs>

      <TabPanel value={tab} index={0}>
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

      <TabPanel value={tab} index={1}>
        <TrackList
          tracks={tracks}
          onDelete={(track) => void checkAndConfirmDelete({ type: 'track', item: track })}
          onEdit={handleTrackEdit}
          sortKey={getSort('tracks').key}
          sortDir={getSort('tracks').dir}
          onSortChange={(key, dir) => setSort('tracks', key, dir)}
          viewMode={getViewMode('tracks') as 'card' | 'list'}
          onViewModeChange={(mode) => setViewMode('tracks', mode)}
          filter={getFilter('tracks')}
          onFilterChange={(val) => setFilter('tracks', val)}
        />
      </TabPanel>

      <TabPanel value={tab} index={2}>
        <StreamList
          streams={streams}
          onDelete={(stream) => void checkAndConfirmDelete({ type: 'stream', item: stream })}
          onUpdate={(s) => setStreams((prev) => prev.map((x) => (x.id === s.id ? s : x)))}
          sortKey={getSort('streams').key}
          sortDir={getSort('streams').dir}
          onSortChange={(key, dir) => setSort('streams', key, dir)}
          viewMode={getViewMode('streams') as 'card' | 'list'}
          onViewModeChange={(mode) => setViewMode('streams', mode)}
        />
      </TabPanel>

      <TabPanel value={tab} index={3}>
        <PodcastList
          podcasts={podcasts}
          onDelete={(podcast) => void checkAndConfirmDelete({ type: 'podcast', item: podcast })}
          onUpdate={(p) => setPodcasts((prev) => prev.map((x) => (x.id === p.id ? p : x)))}
          sortKey={getSort('podcasts').key}
          sortDir={getSort('podcasts').dir}
          onSortChange={(key, dir) => setSort('podcasts', key, dir)}
          viewMode={getViewMode('podcasts') as 'card' | 'list'}
          onViewModeChange={(mode) => setViewMode('podcasts', mode)}
        />
      </TabPanel>

      {/* Central delete dialog */}
      <Dialog open={deleteDialogOpen} onClose={closeDeleteDialog} maxWidth="xs" fullWidth>
        <DialogTitle>{t('media.delete_confirm_title', { defaultValue: 'Medium löschen?' })}</DialogTitle>
        <DialogContent>
          {assignedTagNames.length > 0 ? (
            <DialogContentText>
              {t('media.delete_assigned_warning', { defaultValue: 'Dieses Medium ist noch folgenden RFID-Tags zugewiesen:' })}
              <Box component="ul" sx={{ mt: 1, pl: 2 }}>
                {assignedTagNames.map((name) => <li key={name}>{name}</li>)}
              </Box>
            </DialogContentText>
          ) : (
            <DialogContentText>
              {t('media.delete_confirm_text', { defaultValue: 'Soll dieses Medium wirklich gelöscht werden?' })}
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
                {t('media.delete_media_only', { defaultValue: 'Nur Medium löschen' })}
              </ActionButton>
            )}
            <ActionButton actionType="destructive" onClick={() => void performDelete(assignedTagNames.length > 0)} fullWidth>
              {assignedTagNames.length > 0
                ? t('media.delete_media_and_unassign', { defaultValue: 'Medium + Tag-Zuweisung löschen' })
                : t('delete', { ns: 'common' })}
            </ActionButton>
          </Stack>
        </DialogActions>
      </Dialog>

      {/* Track Edit Dialog */}
      <Dialog open={!!editTrack} onClose={() => { setEditTrack(null); setEditCoverFile(null); }} maxWidth="sm" fullWidth>
        <DialogTitle>{t('tracks.edit')}</DialogTitle>
        <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: '16px !important' }}>
          <CoverUploadField
            displayUrl={editCoverFile ? URL.createObjectURL(editCoverFile) : editTrack?.cover_art_url ?? null}
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
      </Dialog>

      <UploadDialog open={uploadOpen} onClose={() => setUploadOpen(false)}
        onSuccess={(track) => { setTracks((prev) => [...prev, track]); setUploadOpen(false); showSuccess(t('tracks.uploaded')); }} />
      <RemoteTrackDialog open={remoteTrackOpen} onClose={() => setRemoteTrackOpen(false)}
        onSuccess={(track) => { setTracks((prev) => [...prev, track]); setRemoteTrackOpen(false); showSuccess(t('tracks.remote_added', { defaultValue: 'Remote-Track hinzugefügt' })); }} />
      <StreamDialog open={streamOpen} onClose={() => setStreamOpen(false)}
        onSuccess={(stream) => { setStreams((prev) => [...prev, stream]); setStreamOpen(false); showSuccess(t('tracks.stream_added')); }} />
      <PodcastDialog open={podcastOpen} onClose={() => setPodcastOpen(false)}
        onSuccess={(podcast) => { setPodcasts((prev) => [...prev, podcast]); setPodcastOpen(false); showSuccess(t('podcasts.created')); }} />
    </PageShell>
  );
};
