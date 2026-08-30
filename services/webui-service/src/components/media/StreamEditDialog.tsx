import React, { useState } from 'react';
import {
  DialogActions,
  DialogContent,
  DialogTitle,
  TextField,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import { useToast } from '@/contexts/ToastContext';
import type { Stream } from '@/types/api';
import { streamsApi } from '@/api/streams';
import { isValidUrl } from '@/utils/validators';
import { useObjectUrl } from '@/hooks/useObjectUrl';
import { ActionButton } from '@/components/ui/ActionButton';
import { CoverUploadField } from './CoverUploadField';
import { ResponsiveDialog } from '@/components/common/ResponsiveDialog';

interface StreamEditDialogProps {
  open: boolean;
  stream: Stream | null;
  onClose: () => void;
  /** Saved and done - the caller closes the dialog. */
  onSaved: (stream: Stream) => void;
  /**
   * The stream changed while the dialog stays open (the cover was deleted,
   * which happens immediately). Separate from `onSaved` because both used to
   * be the same callback: removing a cover therefore closed the dialog and
   * threw away an edited title along with it.
   */
  onChanged: (stream: Stream) => void;
}

export const StreamEditDialog: React.FC<StreamEditDialogProps> = ({
  open,
  stream,
  onClose,
  onSaved,
  onChanged,
}) => {
  const { t } = useTranslation('media');
  const { showSuccess, showError } = useToast();

  const [title, setTitle] = useState(stream?.title ?? '');
  const [artist, setArtist] = useState(stream?.artist ?? '');
  const [sourceUri, setSourceUri] = useState(stream?.source_uri ?? '');
  const [pendingCoverFile, setPendingCoverFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);

  React.useEffect(() => {
    if (stream && open) {
      setTitle(stream.title);
      setArtist(stream.artist ?? '');
      setSourceUri(stream.source_uri);
      setPendingCoverFile(null);
    }
  }, [stream, open]);

  // A picked file wins over what the server has; once it is uploaded or
  // dropped, the prop is the truth again. No third piece of state in between -
  // the previous `coverUrl` shadowed the prop and had to be kept in sync by
  // hand at four call sites.
  const pendingPreview = useObjectUrl(pendingCoverFile);
  const displayCoverUrl = pendingPreview ?? stream?.cover_art_url ?? null;

  const urlError = sourceUri && !isValidUrl(sourceUri) ? t('invalid_url', { ns: 'errors' }) : '';
  const isValid = title.trim() && sourceUri && isValidUrl(sourceUri);

  const handleSave = async () => {
    if (!stream || !isValid) return;
    setLoading(true);
    try {
      let updated = await streamsApi.update(stream.id, {
        title: title.trim(),
        artist: artist.trim() || null,
        source_uri: sourceUri.trim(),
      });
      if (pendingCoverFile) {
        updated = await streamsApi.uploadCover(stream.id, pendingCoverFile);
      }
      showSuccess(t('streams.updated'));
      onSaved(updated);
    } catch {
      showError(t('streams.update_error'));
    } finally {
      setLoading(false);
    }
  };

  const handleRemoveCover = async () => {
    // A file that was only picked has not been uploaded yet - dropping it needs
    // no request and leaves the stored cover alone.
    if (pendingCoverFile) {
      setPendingCoverFile(null);
      return;
    }
    if (!stream?.cover_art_url) return;
    try {
      const updated = await streamsApi.deleteCover(stream.id);
      onChanged(updated);
      showSuccess(t('streams.cover_removed'));
    } catch {
      showError(t('streams.cover_error'));
    }
  };

  return (
    <ResponsiveDialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ fontSize: '1.25rem', fontWeight: 600 }}>
        {t('streams.edit')}
      </DialogTitle>
      <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: '16px !important' }}>
        <CoverUploadField
          displayUrl={displayCoverUrl}
          coverFile={pendingCoverFile}
          onFileSelect={setPendingCoverFile}
          onRemove={handleRemoveCover}
        />

        <TextField
          label={t('streams.fields.title')}
          placeholder={t('stream.fields.title_placeholder')}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          fullWidth
          size="small"
          required
        />
        <TextField
          label={t('streams.fields.artist')}
          value={artist}
          onChange={(e) => setArtist(e.target.value)}
          fullWidth
          size="small"
        />
        <TextField
          label={t('stream.url')}
          value={sourceUri}
          onChange={(e) => setSourceUri(e.target.value)}
          fullWidth
          size="small"
          error={!!urlError}
          helperText={urlError}
          required
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
