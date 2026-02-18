import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  InputAdornment,
  Snackbar,
  TextField,
  Typography,
} from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import { useTranslation } from 'react-i18next';
import { TagList } from '@/components/rfid/TagList';
import { TagEditDialog } from '@/components/rfid/TagEditDialog';
import { LearnModeButton } from '@/components/rfid/LearnModeButton';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { tagsApi } from '@/api/tags';
import { playlistsApi } from '@/api/playlists';
import { tracksApi } from '@/api/tracks';
import { useWebSocket } from '@/contexts/WebSocketContext';
import type { Tag, Playlist, Track, ContentType, RFIDScannedMessage } from '@/types/api';

export const RfidPage: React.FC = () => {
  const { t } = useTranslation('rfid');
  const { lastMessage } = useWebSocket();

  const [tags, setTags] = useState<Tag[]>([]);
  const [playlists, setPlaylists] = useState<Playlist[]>([]);
  const [tracks, setTracks] = useState<Track[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');

  const [learnModeActive, setLearnModeActive] = useState(false);
  const [learnModeLoading, setLearnModeLoading] = useState(false);
  const [scannedTagId, setScannedTagId] = useState<string | null>(null);

  const [editTag, setEditTag] = useState<Tag | null>(null);
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [deleteTag, setDeleteTag] = useState<Tag | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [tagsData, playlistsData, tracksData] = await Promise.all([
        tagsApi.getAll(),
        playlistsApi.getAll(),
        tracksApi.getAll(),
      ]);
      setTags(tagsData);
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

  // Listen for WebSocket RFID learning mode events
  useEffect(() => {
    if (lastMessage?.type === 'rfid_scanned_learning') {
      const msg = lastMessage as RFIDScannedMessage;
      setScannedTagId(msg.data.tag_id);
      setLearnModeLoading(false);
      setEditDialogOpen(true);
      setEditTag(null);
    }
  }, [lastMessage]);

  const handleLearnModeActivate = async () => {
    setLearnModeLoading(true);
    try {
      await tagsApi.setLearningMode(true);
      setLearnModeActive(true);
    } catch {
      setError('Lern-Modus konnte nicht aktiviert werden');
      setLearnModeLoading(false);
    }
  };

  const handleLearnModeDeactivate = async () => {
    try {
      await tagsApi.setLearningMode(false);
    } catch {
      // ignore
    } finally {
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
  }) => {
    try {
      if (editTag) {
        // Update existing tag (backend expects RFID tag_id in URL)
        const updated = await tagsApi.update(editTag.tag_id, data);
        setTags((prev) => prev.map((t) => (t.tag_id === updated.tag_id ? updated : t)));
        setSuccessMessage('Tag aktualisiert');
      } else if (scannedTagId) {
        // Create new tag from learn mode
        const newTag = await tagsApi.create({ tag_id: scannedTagId, ...data });
        setTags((prev) => [...prev, newTag]);
        setSuccessMessage('Tag gespeichert');
        setLearnModeActive(false);
        await tagsApi.setLearningMode(false);
      }
    } catch {
      setError('Tag konnte nicht gespeichert werden');
    } finally {
      setEditDialogOpen(false);
      setEditTag(null);
      setScannedTagId(null);
    }
  };

  const handleDeleteConfirm = async () => {
    if (!deleteTag) return;
    try {
      await tagsApi.delete(deleteTag.tag_id);
      setTags((prev) => prev.filter((t) => t.tag_id !== deleteTag!.tag_id));
      setSuccessMessage('Tag gelöscht');
    } catch {
      setError('Tag konnte nicht gelöscht werden');
    } finally {
      setDeleteTag(null);
    }
  };

  const filteredTags = tags.filter((tag) => {
    const q = searchQuery.toLowerCase();
    return (
      tag.tag_id.toLowerCase().includes(q) ||
      (tag.name ?? '').toLowerCase().includes(q)
    );
  });

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

      {/* Actions Row */}
      <Box display="flex" gap={2} mb={3} flexWrap="wrap" alignItems="flex-start">
        <TextField
          placeholder={t('search_placeholder')}
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          size="small"
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon />
              </InputAdornment>
            ),
          }}
          sx={{ minWidth: 240 }}
        />
        <LearnModeButton
          active={learnModeActive}
          loading={learnModeLoading}
          onActivate={handleLearnModeActivate}
          onDeactivate={handleLearnModeDeactivate}
        />
      </Box>

      {/* Tag List */}
      <TagList
        tags={filteredTags}
        playlists={playlists}
        tracks={tracks}
        onEdit={handleEditOpen}
        onDelete={setDeleteTag}
      />

      {/* Edit / Create Dialog */}
      <TagEditDialog
        open={editDialogOpen}
        tag={editTag}
        newTagId={scannedTagId}
        playlists={playlists}
        tracks={tracks}
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

      {/* Delete Confirmation Dialog */}
      <Dialog open={!!deleteTag} onClose={() => setDeleteTag(null)}>
        <DialogTitle sx={{ fontSize: '1.25rem', fontWeight: 600 }}>{t('delete_tag')}</DialogTitle>
        <DialogContent>
          <DialogContentText>
            {t('delete_confirm', { name: deleteTag?.name ?? deleteTag?.tag_id })}
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteTag(null)}>{t('cancel', { ns: 'common' })}</Button>
          <Button onClick={handleDeleteConfirm} color="error" variant="contained">
            {t('delete', { ns: 'common' })}
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar
        open={!!successMessage}
        autoHideDuration={3000}
        onClose={() => setSuccessMessage(null)}
        message={successMessage}
      />
    </Box>
  );
};
