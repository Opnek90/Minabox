import React, { useState } from 'react';
import {
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  TextField,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import { useToast } from '@/contexts/ToastContext';
import type { Podcast } from '@/types/api';
import { podcastsApi } from '@/api/podcasts';
import { isValidUrl } from '@/utils/validators';
import { CoverUploadField } from './CoverUploadField';

interface PodcastEditDialogProps {
  open: boolean;
  podcast: Podcast | null;
  onClose: () => void;
  onSuccess: (podcast: Podcast) => void;
}

export const PodcastEditDialog: React.FC<PodcastEditDialogProps> = ({
  open,
  podcast,
  onClose,
  onSuccess,
}) => {
  const { t } = useTranslation('media');
  const { showSuccess, showError } = useToast();

  const [title, setTitle] = useState(podcast?.title ?? '');
  const [rssUrl, setRssUrl] = useState(podcast?.rss_url ?? '');
  const [description, setDescription] = useState(podcast?.description ?? '');
  const [coverUrl, setCoverUrl] = useState<string | null>(podcast?.cover_art_url ?? null);
  const [pendingCoverFile, setPendingCoverFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);

  React.useEffect(() => {
    if (podcast && open) {
      setTitle(podcast.title);
      setRssUrl(podcast.rss_url);
      setDescription(podcast.description ?? '');
      setCoverUrl(podcast.cover_art_url ?? null);
      setPendingCoverFile(null);
    }
  }, [podcast, open]);

  const urlError = rssUrl && !isValidUrl(rssUrl) ? t('invalid_url', { ns: 'errors' }) : '';
  const isValid = title.trim() && rssUrl && isValidUrl(rssUrl);

  const handleSave = async () => {
    if (!podcast || !isValid) return;
    setLoading(true);
    try {
      let updated = await podcastsApi.update(podcast.id, {
        title: title.trim(),
        rss_url: rssUrl.trim(),
        description: description.trim() || null,
      });
      if (pendingCoverFile) {
        updated = await podcastsApi.uploadCover(podcast.id, pendingCoverFile);
      }
      onSuccess(updated);
      showSuccess(t('podcasts.updated', { defaultValue: 'Podcast aktualisiert' }));
      onClose();
    } catch {
      showError(t('podcasts.update_error', { defaultValue: 'Podcast konnte nicht gespeichert werden' }));
    } finally {
      setLoading(false);
    }
  };

  const handleRemoveCover = async () => {
    if (!podcast) return;
    setCoverUrl(null);
    setPendingCoverFile(null);
    try {
      const updated = await podcastsApi.deleteCover(podcast.id);
      setCoverUrl(updated.cover_art_url ?? null);
      onSuccess(updated);
      showSuccess(t('podcasts.cover_removed', { defaultValue: 'Cover entfernt' }));
    } catch {
      showError(t('podcasts.cover_error', { defaultValue: 'Cover konnte nicht entfernt werden' }));
    }
  };

  const handleCoverSelect = (file: File | null) => {
    if (file) {
      setPendingCoverFile(file);
      setCoverUrl(URL.createObjectURL(file));
    } else {
      setPendingCoverFile(null);
      setCoverUrl(podcast?.cover_art_url ?? null);
    }
  };

  const handleRemoveCoverInField = () => {
    if (pendingCoverFile) {
      setPendingCoverFile(null);
      setCoverUrl(podcast?.cover_art_url ?? null);
    } else {
      handleRemoveCover();
    }
  };

  const displayCoverUrl = pendingCoverFile ? coverUrl : (coverUrl ?? podcast?.cover_art_url ?? null);

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ fontSize: '1.25rem', fontWeight: 600 }}>
        {t('podcasts.edit', { defaultValue: 'Podcast bearbeiten' })}
      </DialogTitle>
      <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: '16px !important' }}>
        <CoverUploadField
          displayUrl={displayCoverUrl}
          coverFile={pendingCoverFile}
          onFileSelect={handleCoverSelect}
          onRemove={handleRemoveCoverInField}
        />

        <TextField
          label={t('podcasts.fields.title')}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          fullWidth
          size="small"
          required
        />
        <TextField
          label={t('podcasts.fields.rss_url')}
          value={rssUrl}
          onChange={(e) => setRssUrl(e.target.value)}
          fullWidth
          size="small"
          error={!!urlError}
          helperText={urlError}
          required
        />
        <TextField
          label={t('podcasts.fields.description', { defaultValue: 'Beschreibung' })}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          fullWidth
          size="small"
          multiline
          rows={2}
        />
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('cancel', { ns: 'common' })}</Button>
        <Button onClick={handleSave} variant="contained" disabled={!isValid || loading}>
          {t('save', { ns: 'common' })}
        </Button>
      </DialogActions>
    </Dialog>
  );
};
