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
import { podcastsApi } from '@/api/podcasts';
import type { Podcast } from '@/types/api';
import { isValidUrl } from '@/utils/validators';

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
  const { t } = useTranslation('media');
  const { showError } = useToast();
  const [title, setTitle] = useState('');
  const [rssUrl, setRssUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const urlError = rssUrl && !isValidUrl(rssUrl) ? t('invalid_url', { ns: 'errors' }) : '';
  const isValid = title.trim() && rssUrl && isValidUrl(rssUrl);

  const handleSave = async () => {
    if (!isValid) return;
    setLoading(true);
    try {
      const podcast = await podcastsApi.create({ title: title.trim(), rss_url: rssUrl.trim() });
      onSuccess(podcast);
      setTitle('');
      setRssUrl('');
      onClose();
    } catch {
      showError(t('podcasts.create_error', { defaultValue: 'Podcast could not be added' }));
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    setTitle('');
    setRssUrl('');
    onClose();
  };

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ fontSize: '1.25rem', fontWeight: 600 }}>
        {t('podcasts.add', { defaultValue: 'Add Podcast' })}
      </DialogTitle>
      <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: '16px !important' }}>
        <TextField
          label={t('podcasts.fields.title', { defaultValue: 'Title' })}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          fullWidth
          size="small"
          required
        />
        <TextField
          label={t('podcasts.fields.rss_url', { defaultValue: 'RSS Feed URL' })}
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
          {t('add', { ns: 'common' })}
        </Button>
      </DialogActions>
    </Dialog>
  );
};
