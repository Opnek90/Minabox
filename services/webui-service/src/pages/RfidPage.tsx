import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  InputAdornment,
  TextField,
} from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import { useTranslation } from 'react-i18next';
import { TagList } from '@/components/rfid/TagList';
import { TagEditDialog } from '@/components/rfid/TagEditDialog';
import { LearnModeButton } from '@/components/rfid/LearnModeButton';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { PageShell } from '@/components/common/PageShell';
import { useToast } from '@/contexts/ToastContext';
import { tagsApi } from '@/api/tags';
import { playlistsApi } from '@/api/playlists';
import { podcastsApi } from '@/api/podcasts';
import { streamsApi } from '@/api/streams';
import { tracksApi } from '@/api/tracks';
import { useWebSocket } from '@/contexts/WebSocketContext';
import type { Tag, Playlist, Podcast, Stream, Track, ContentType, RFIDScannedMessage } from '@/types/api';


interface RfidPageProps {
  pendingTagId?: string | null;
  onPendingTagHandled?: () => void;
}


export const RfidPage: React.FC<RfidPageProps> = ({
  pendingTagId,
  onPendingTagHandled,
}) => {
  const { t } = useTranslation('rfid');
  const { lastMessage } = useWebSocket();
  const { showSuccess, showError } = useToast();

  const [tags, setTags] = useState<Tag[]>([]);
  const [playlists, setPlaylists] = useState<Playlist[]>([]);
  const [tracks, setTracks] = useState<Track[]>([]);
  const [streams, setStreams] = useState<Stream[]>([]);
  const [podcasts, setPodcasts] = useState<Podcast[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');

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
      setError('Fehler beim Laden der Daten');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Lern-Modus: Karte gescannt → TagEditDialog öffnen
  useEffect(() => {
    if (lastMessage?.type === 'rfid_scanned_learning') {
      const msg = lastMessage as RFIDScannedMessage;
      setScannedTagId(msg.data.tag_id);
      setLearnModeLoading(false);
      setEditDialogOpen(true);
      setEditTag(null);
    }
  }, [lastMessage]);

  // Drawer → "Zuweisen" gedrückt: pendingTagId kommt rein
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
        const updated = await tagsApi.update(editTag.tag_id, data);
        setTags((prev) => prev.map((t) => (t.tag_id === updated.tag_id ? updated : t)));
        showSuccess(t('toast.tag_updated', { defaultValue: 'Tag aktualisiert' }));
      } else if (scannedTagId) {
        const newTag = await tagsApi.create({ tag_id: scannedTagId, ...data });
        setTags((prev) => [...prev, newTag]);
        showSuccess(t('toast.tag_saved', { defaultValue: 'Tag gespeichert' }));
        setLearnModeActive(false);
        await tagsApi.setLearningMode(false);
      }
    } catch {
      showError(t('toast.tag_save_error', { defaultValue: 'Tag konnte nicht gespeichert werden' }));
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
      setTags((prev) => prev.filter((t) => t.tag_id !== deleteTag.tag_id));
      showSuccess(t('toast.tag_deleted', { defaultValue: 'Tag gelöscht' }));
    } catch {
      showError(t('toast.tag_delete_error', { defaultValue: 'Tag konnte nicht gelöscht werden' }));
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
      {error && (
        <Alert severity="error" onClose={() => setError(null)} sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      {/* Search */}
      <TextField
        placeholder={t('search_placeholder')}
        value={searchQuery}
        onChange={(e) => setSearchQuery(e.target.value)}
        size="small"
        fullWidth
        InputProps={{
          startAdornment: (
            <InputAdornment position="start">
              <SearchIcon />
            </InputAdornment>
          ),
        }}
        sx={{ mb: 3, maxWidth: 400 }}
      />

      {/* Tag List */}
      <TagList
        tags={filteredTags}
        playlists={playlists}
        tracks={tracks}
        streams={streams}
        podcasts={podcasts}
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

      {/* Delete Confirmation Dialog */}
      <Dialog open={!!deleteTag} onClose={() => setDeleteTag(null)}>
        <DialogTitle>{t('delete_tag')}</DialogTitle>
        <DialogContent>
          <DialogContentText>
            {t('delete_confirm', { name: deleteTag?.name ?? deleteTag?.tag_id })}
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteTag(null)}>
            {t('cancel', { ns: 'common' })}
          </Button>
          <Button onClick={handleDeleteConfirm} color="error" variant="contained">
            {t('delete', { ns: 'common' })}
          </Button>
        </DialogActions>
      </Dialog>
    </PageShell>
  );
};
