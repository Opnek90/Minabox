import React, { useState } from 'react';
import {
  Button,
  DialogActions,
  DialogContent,
  DialogTitle,
  TextField,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import { useToast } from '@/contexts/ToastContext';
import { podcastsApi } from '@/api/podcasts';
import type { Podcast } from '@/types/api';
import { isValidUrl } from '@/utils/validators';
import { CoverUploadField } from './CoverUploadField';
import { ResponsiveDialog } from '@/components/common/ResponsiveDialog';

interface PodcastDialogProps {
  open: boolean;
  onClose: () => void;
  onSuccess: (podcast: Podcast) => void;
}

export const PodcastDialog: React.FC<PodcastDialogProps> = ({
  open,
  onClose,
  onSuccess,
}) => {
  const { t } = useTranslation(['media', 'common']);
  const { showError } = useToast();
  const [title, setTitle] = useState('');
  const [rssUrl, setRssUrl] = useState('');
  const [coverFile, setCoverFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const urlError = rssUrl && !isValidUrl(rssUrl) ? t('invalid_url', { ns: 'errors' }) : '';
  const isValid = title.trim() && rssUrl && isValidUrl(rssUrl);

  const handleSave = async () => {
    if (!isValid) return;
    setLoading(true);
    try {
      let podcast = await podcastsApi.create({ title: title.trim(), rss_url: rssUrl.trim() });
      if (coverFile) {
        podcast = await podcastsApi.uploadCover(podcast.id, coverFile);
      }
      onSuccess(podcast);
      setTitle('');
      setRssUrl('');
      setCoverFile(null);
      onClose();
    } catch {
      showError(t('podcasts.create_error'));
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    setTitle('');
    setRssUrl('');
    setCoverFile(null);
    onClose();
  };

  return (
    <ResponsiveDialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ fontSize: '1.25rem', fontWeight: 600 }}>
        {t('podcasts.add')}
      </DialogTitle>
      <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: '16px !important' }}>
        <CoverUploadField
          displayUrl={coverFile ? URL.createObjectURL(coverFile) : null}
          coverFile={coverFile}
          onFileSelect={(file) => setCoverFile(file)}
          onRemove={() => setCoverFile(null)}
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
      </DialogContent>
      <DialogActions>
        <Button onClick={handleClose}>{t('cancel', { ns: 'common' })}</Button>
        <Button onClick={handleSave} variant="contained" disabled={!isValid || loading}>
          {t('common:actions.add')}
        </Button>
      </DialogActions>
    </ResponsiveDialog>
  );
};
