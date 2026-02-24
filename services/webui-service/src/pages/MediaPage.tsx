import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Tab,
  Tabs,
  TextField,
} from '@mui/material';
import CloudUploadIcon from '@mui/icons-material/CloudUpload';
import LinkIcon from '@mui/icons-material/Link';
import PodcastsIcon from '@mui/icons-material/Podcasts';
import StreamIcon from '@mui/icons-material/Stream';
import { useTranslation } from 'react-i18next';
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
import { playlistsApi } from '@/api/playlists';
import { podcastsApi } from '@/api/podcasts';
import { streamsApi } from '@/api/streams';
import { tracksApi } from '@/api/tracks';
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


export const MediaPage: React.FC = () => {
  const { t } = useTranslation('media');
  const { showSuccess, showError } = useToast();
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

  const [editTrack, setEditTrack] = useState<Track | null>(null);
  const [editForm, setEditForm] = useState({ title: '', artist: '', album: '' });
  const [editCoverFile, setEditCoverFile] = useState<File | null>(null);
  const [editSaving, setEditSaving] = useState(false);

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

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleTrackDelete = async (track: Track) => {
    try {
      await tracksApi.delete(track.id);
      setTracks((prev) => prev.filter((tr) => tr.id !== track.id));
      showSuccess(t('tracks.deleted'));
    } catch {
      showError(t('tracks.delete_error'));
    }
  };

  const handleTrackEdit = (track: Track) => {
    setEditTrack(track);
    setEditForm({
      title: track.title,
      artist: track.artist ?? '',
      album: track.album ?? '',
    });
    setEditCoverFile(null);
  };

  const handleStreamDelete = async (stream: Stream) => {
    try {
      await streamsApi.delete(stream.id);
      setStreams((prev) => prev.filter((s) => s.id !== stream.id));
      showSuccess(t('streams.deleted', { defaultValue: 'Stream gelöscht' }));
    } catch {
      showError(t('streams.delete_error', { defaultValue: 'Stream konnte nicht gelöscht werden' }));
    }
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
      if (editCoverFile) {
        updated = await tracksApi.uploadCover(editTrack.id, editCoverFile);
      }
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
    if (editCoverFile) {
      setEditCoverFile(null);
      return;
    }
    if (editTrack?.cover_art_url) {
      tracksApi
        .deleteCover(editTrack.id)
        .then((updated) => {
          setTracks((prev) => prev.map((tr) => (tr.id === updated.id ? updated : tr)));
          setEditTrack(updated);
        })
        .catch(() => showError(t('tracks.update_error')));
    }
  };

  if (loading) return <LoadingSpinner message={t('title')} fullPage />;

  return (
    <PageShell
      title={t('title')}
      actions={
        tab === 1 ? (
          <>
            <Button
              variant="outlined"
              size="small"
              startIcon={<LinkIcon />}
              onClick={() => setRemoteTrackOpen(true)}
            >
              {t('tracks.add_remote', { defaultValue: 'Remote-Track' })}
            </Button>
            <Button
              variant="contained"
              size="small"
              startIcon={<CloudUploadIcon />}
              onClick={() => setUploadOpen(true)}
            >
              {t('tracks.upload')}
            </Button>
          </>
        ) : tab === 2 ? (
          <Button
            variant="contained"
            size="small"
            startIcon={<StreamIcon />}
            onClick={() => setStreamOpen(true)}
          >
            {t('tracks.add_stream')}
          </Button>
        ) : tab === 3 ? (
          <Button
            variant="contained"
            size="small"
            startIcon={<PodcastsIcon />}
            onClick={() => setPodcastOpen(true)}
          >
            {t('podcasts.add')}
          </Button>
        ) : undefined
      }
    >
      {error && (
        <Alert severity="error" onClose={() => setError(null)} sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      <Tabs
        value={tab}
        onChange={(_, v) => setTab(v)}
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
        />
      </TabPanel>

      <TabPanel value={tab} index={1}>
        <TrackList
          tracks={tracks}
          onDelete={handleTrackDelete}
          onEdit={handleTrackEdit}
        />
      </TabPanel>

      <TabPanel value={tab} index={2}>
        <StreamList
          streams={streams}
          onDelete={handleStreamDelete}
          onUpdate={(s) => setStreams((prev) => prev.map((x) => (x.id === s.id ? s : x)))}
        />
      </TabPanel>

      <TabPanel value={tab} index={3}>
        <PodcastList
          podcasts={podcasts}
          onDelete={async (podcast) => {
            try {
              await podcastsApi.delete(podcast.id);
              setPodcasts((prev) => prev.filter((p) => p.id !== podcast.id));
              showSuccess(t('podcasts.deleted'));
            } catch {
              showError(t('podcasts.delete_error'));
            }
          }}
          onUpdate={(p) => setPodcasts((prev) => prev.map((x) => (x.id === p.id ? p : x)))}
        />
      </TabPanel>

      {/* Track Edit Dialog */}
      <Dialog open={!!editTrack} onClose={() => { setEditTrack(null); setEditCoverFile(null); }} maxWidth="sm" fullWidth>
        <DialogTitle>{t('tracks.edit')}</DialogTitle>
        <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: '16px !important' }}>
          <CoverUploadField
            displayUrl={
              editCoverFile
                ? URL.createObjectURL(editCoverFile)
                : editTrack?.cover_art_url ?? null
            }
            coverFile={editCoverFile}
            onFileSelect={(file) => setEditCoverFile(file)}
            onRemove={handleTrackEditRemoveCover}
          />
          <TextField
            label={t('tracks.fields.title')}
            value={editForm.title}
            onChange={(e) => setEditForm((p) => ({ ...p, title: e.target.value }))}
            size="small"
            fullWidth
            required
          />
          <TextField
            label={t('tracks.fields.artist')}
            value={editForm.artist}
            onChange={(e) => setEditForm((p) => ({ ...p, artist: e.target.value }))}
            size="small"
            fullWidth
          />
          <TextField
            label={t('tracks.fields.album')}
            value={editForm.album}
            onChange={(e) => setEditForm((p) => ({ ...p, album: e.target.value }))}
            size="small"
            fullWidth
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditTrack(null)}>
            {t('cancel', { ns: 'common' })}
          </Button>
          <Button
            variant="contained"
            onClick={handleTrackEditSave}
            disabled={editSaving || !editForm.title.trim()}
          >
            {t('save', { ns: 'common' })}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Upload Dialog */}
      <UploadDialog
        open={uploadOpen}
        onClose={() => setUploadOpen(false)}
        onSuccess={(track) => {
          setTracks((prev) => [...prev, track]);
          setUploadOpen(false);
          showSuccess(t('tracks.uploaded'));
        }}
      />

      {/* Remote Track Dialog */}
      <RemoteTrackDialog
        open={remoteTrackOpen}
        onClose={() => setRemoteTrackOpen(false)}
        onSuccess={(track) => {
          setTracks((prev) => [...prev, track]);
          setRemoteTrackOpen(false);
          showSuccess(t('tracks.remote_added', { defaultValue: 'Remote-Track hinzugefügt' }));
        }}
      />

      {/* Stream Dialog */}
      <StreamDialog
        open={streamOpen}
        onClose={() => setStreamOpen(false)}
        onSuccess={(stream) => {
          setStreams((prev) => [...prev, stream]);
          setStreamOpen(false);
          showSuccess(t('tracks.stream_added'));
        }}
      />

      {/* Podcast Dialog */}
      <PodcastDialog
        open={podcastOpen}
        onClose={() => setPodcastOpen(false)}
        onSuccess={(podcast) => {
          setPodcasts((prev) => [...prev, podcast]);
          setPodcastOpen(false);
          showSuccess(t('podcasts.created'));
        }}
      />
    </PageShell>
  );
};
