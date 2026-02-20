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
import StreamIcon from '@mui/icons-material/Stream';
import { useTranslation } from 'react-i18next';
import { PlaylistList } from '@/components/media/PlaylistList';
import { RemoteTrackDialog } from '@/components/media/RemoteTrackDialog';
import { StreamDialog } from '@/components/media/StreamDialog';
import { StreamList } from '@/components/media/StreamList';
import { TrackList } from '@/components/media/TrackList';
import { UploadDialog } from '@/components/media/UploadDialog';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { PageShell } from '@/components/common/PageShell';
import { useToast } from '@/contexts/ToastContext';
import { playlistsApi } from '@/api/playlists';
import { streamsApi } from '@/api/streams';
import { tracksApi } from '@/api/tracks';
import type { Playlist, Stream, Track } from '@/types/api';


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
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [remoteTrackOpen, setRemoteTrackOpen] = useState(false);
  const [streamOpen, setStreamOpen] = useState(false);

  const [editTrack, setEditTrack] = useState<Track | null>(null);
  const [editForm, setEditForm] = useState({ title: '', artist: '', album: '' });
  const [editSaving, setEditSaving] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [playlistsData, tracksData, streamsData] = await Promise.all([
        playlistsApi.getAll(),
        tracksApi.getAll(),
        streamsApi.getAll(),
      ]);
      setPlaylists(playlistsData);
      setTracks(tracksData);
      setStreams(streamsData);
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
      const updated = await tracksApi.update(editTrack.id, {
        title: editForm.title.trim() || editTrack.title,
        artist: editForm.artist.trim() || null,
        album: editForm.album.trim() || null,
      });
      setTracks((prev) => prev.map((tr) => (tr.id === updated.id ? updated : tr)));
      setEditTrack(null);
      showSuccess(t('tracks.updated'));
    } catch {
      showError(t('tracks.update_error'));
    } finally {
      setEditSaving(false);
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
        <StreamList streams={streams} onDelete={handleStreamDelete} />
      </TabPanel>

      {/* Track Edit Dialog */}
      <Dialog open={!!editTrack} onClose={() => setEditTrack(null)} maxWidth="sm" fullWidth>
        <DialogTitle>{t('tracks.edit')}</DialogTitle>
        <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: '16px !important' }}>
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
    </PageShell>
  );
};
