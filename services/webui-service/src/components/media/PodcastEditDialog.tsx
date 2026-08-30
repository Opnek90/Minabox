import React, { useState } from 'react';
import {
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
import { useObjectUrl } from '@/hooks/useObjectUrl';
import { ActionButton } from '@/components/ui/ActionButton';
import { CoverUploadField } from './CoverUploadField';
import { ResponsiveDialog } from '@/components/common/ResponsiveDialog';

interface PodcastEditDialogProps {
  open: boolean;
  podcast: Podcast | null;
  onClose: () => void;
  /** Saved and done - the caller closes the dialog. */
  onSaved: (podcast: Podcast) => void;
  /** The podcast changed while the dialog stays open; see StreamEditDialog. */
  onChanged: (podcast: Podcast) => void;
}

export const PodcastEditDialog: React.FC<PodcastEditDialogProps> = ({
  open,
  podcast,
  onClose,
  onSaved,
  onChanged,
}) => {
  const { t } = useTranslation('media');
  const { showSuccess, showError } = useToast();

  const [title, setTitle] = useState(podcast?.title ?? '');
  const [rssUrl, setRssUrl] = useState(podcast?.rss_url ?? '');
  const [description, setDescription] = useState(podcast?.description ?? '');
  const [pendingCoverFile, setPendingCoverFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);

  React.useEffect(() => {
    if (podcast && open) {
      setTitle(podcast.title);
      setRssUrl(podcast.rss_url);
      setDescription(podcast.description ?? '');
      setPendingCoverFile(null);
    }
  }, [podcast, open]);

  const pendingPreview = useObjectUrl(pendingCoverFile);
  const displayCoverUrl = pendingPreview ?? podcast?.cover_art_url ?? null;

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
      showSuccess(t('podcasts.updated'));
      onSaved(updated);
    } catch {
      showError(t('podcasts.update_error'));
    } finally {
      setLoading(false);
    }
  };

  const handleRemoveCover = async () => {
    if (pendingCoverFile) {
      setPendingCoverFile(null);
      return;
    }
    if (!podcast?.cover_art_url) return;
    try {
      const updated = await podcastsApi.deleteCover(podcast.id);
      onChanged(updated);
      showSuccess(t('podcasts.cover_removed'));
    } catch {
      showError(t('podcasts.cover_error'));
    }
  };

  return (
    <ResponsiveDialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ fontSize: '1.25rem', fontWeight: 600 }}>
        {t('podcasts.edit')}
      </DialogTitle>
      <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: '16px !important' }}>
        <CoverUploadField
          displayUrl={displayCoverUrl}
          coverFile={pendingCoverFile}
          onFileSelect={setPendingCoverFile}
          onRemove={handleRemoveCover}
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
          label={t('podcasts.fields.description')}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          fullWidth
          size="small"
          multiline
          rows={2}
        />
      </DialogContent>
      <DialogActions>
        <ActionButton actionType="secondary" onClick={onClose}>
          {t('cancel', { ns: 'common' })}
        </ActionButton>
        <ActionButton
          actionType="primary"
          onClick={handleSave}
          loading={loading}
          disabled={!isValid || loading}
        >
          {t('save', { ns: 'common' })}
        </ActionButton>
      </DialogActions>
    </ResponsiveDialog>
  );
};
