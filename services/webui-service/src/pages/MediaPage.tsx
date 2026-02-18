import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Snackbar,
  Tab,
  Tabs,
  TextField,
  Typography,
} from '@mui/material';
import CloudUploadIcon from '@mui/icons-material/CloudUpload';
import StreamIcon from '@mui/icons-material/Stream';
import { useTranslation } from 'react-i18next';
import { PlaylistList } from '@/components/media/PlaylistList';
import { TrackList } from '@/components/media/TrackList';
import { UploadDialog } from '@/components/media/UploadDialog';
import { StreamDialog } from '@/components/media/StreamDialog';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { playlistsApi } from '@/api/playlists';
import { tracksApi } from '@/api/tracks';
import type { Playlist, Track } from '@/types/api';

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
  const [tab, setTab] = useState(0);
  const [playlists, setPlaylists] = useState<Playlist[]>([]);
  const [tracks, setTracks] = useState<Track[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [streamOpen, setStreamOpen] = useState(false);

  // Track edit state
  const [editTrack, setEditTrack] = useState<Track | null>(null);
  const [editForm, setEditForm] = useState({ title: '', artist: '', album: '' });
  const [editSaving, setEditSaving] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [playlistsData, tracksData] = await Promise.all([
        playlistsApi.getAll(),
        tracksApi.getAll(),
      ]);
      setPlaylists(playlistsData);
      setTracks(tracksData);
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
      setSuccessMessage(t('tracks.deleted'));
    } catch {
      setError(t('tracks.delete_error'));
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
      setSuccessMessage(t('tracks.updated'));
    } catch {
      setError(t('tracks.update_error'));
    } finally {
      setEditSaving(false);
    }
  };

  if (loading) return <LoadingSpinner message={t('title')} fullPage />;

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h5" fontWeight={700} gutterBottom>
        {t('title')}
      </Typography>

      {error && (
        <Alert severity="error" onClose={() => setError(null)} sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ borderBottom: 1, borderColor: 'divider' }}>
        <Tab label={t('tabs.playlists')} />
        <Tab label={t('tabs.tracks')} />
      </Tabs>

      {/* Playlists Tab */}
      <TabPanel value={tab} index={0}>
        <PlaylistList
          playlists={playlists}
          tracks={tracks}
          onUpdate={(pl) => setPlaylists((prev) => prev.map((p) => (p.id === pl.id ? pl : p)))}
          onDelete={(pl) => setPlaylists((prev) => prev.filter((p) => p.id !== pl.id))}
          onCreate={(pl) => setPlaylists((prev) => [...prev, pl])}
        />
      </TabPanel>

      {/* Tracks Tab */}
      <TabPanel value={tab} index={1}>
        <Box display="flex" gap={2} mb={2} justifyContent="flex-end" flexWrap="wrap">
          <Button variant="outlined" startIcon={<StreamIcon />} onClick={() => setStreamOpen(true)}>
            {t('tracks.add_stream')}
          </Button>
          <Button variant="contained" startIcon={<CloudUploadIcon />} onClick={() => setUploadOpen(true)}>
            {t('tracks.upload')}
          </Button>
        </Box>
        <TrackList
          tracks={tracks}
          onDelete={handleTrackDelete}
          onEdit={handleTrackEdit}
        />
      </TabPanel>

      {/* Track Edit Dialog */}
      <Dialog open={!!editTrack} onClose={() => setEditTrack(null)} maxWidth="sm" fullWidth>
        <DialogTitle sx={{ fontWeight: 600 }}>{t('tracks.edit')}</DialogTitle>
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
          <Button onClick={() => setEditTrack(null)}>{t('cancel', { ns: 'common' })}</Button>
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
          setSuccessMessage(t('tracks.uploaded'));
        }}
      />

      {/* Stream Dialog */}
      <StreamDialog
        open={streamOpen}
        onClose={() => setStreamOpen(false)}
        onSuccess={(track) => {
          setTracks((prev) => [...prev, track]);
          setStreamOpen(false);
          setSuccessMessage(t('tracks.stream_added'));
        }}
      />

      <Snackbar
        open={!!successMessage}
        autoHideDuration={3000}
        onClose={() => setSuccessMessage(null)}
        message={successMessage}
      />
    </Box>
  );
};
