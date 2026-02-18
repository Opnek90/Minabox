import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Snackbar,
  Tab,
  Tabs,
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
      setError('Fehler beim Laden der Daten');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleTrackDelete = async (track: Track) => {
    try {
      await tracksApi.delete(track.id);
      setTracks((prev) => prev.filter((t) => t.id !== track.id));
      setSuccessMessage('Track gelöscht');
    } catch {
      setError('Track konnte nicht gelöscht werden');
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
          <Button
            variant="outlined"
            startIcon={<StreamIcon />}
            onClick={() => setStreamOpen(true)}
          >
            {t('tracks.add_stream')}
          </Button>
          <Button
            variant="contained"
            startIcon={<CloudUploadIcon />}
            onClick={() => setUploadOpen(true)}
          >
            {t('tracks.upload')}
          </Button>
        </Box>
        <TrackList
          tracks={tracks}
          onDelete={handleTrackDelete}
        />
      </TabPanel>

      {/* Upload Dialog */}
      <UploadDialog
        open={uploadOpen}
        onClose={() => setUploadOpen(false)}
        onSuccess={(track) => {
          setTracks((prev) => [...prev, track]);
          setUploadOpen(false);
          setSuccessMessage('Track hochgeladen');
        }}
      />

      {/* Stream Dialog */}
      <StreamDialog
        open={streamOpen}
        onClose={() => setStreamOpen(false)}
        onSuccess={(track) => {
          setTracks((prev) => [...prev, track]);
          setStreamOpen(false);
          setSuccessMessage('Stream hinzugefügt');
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
