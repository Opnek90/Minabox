import React, { useEffect, useState } from 'react';
import {
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  TextField,
  Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import type { Tag, ContentType, Playlist, Stream, Track } from '@/types/api';

interface TagEditDialogProps {
  open: boolean;
  tag: Tag | null;
  /** For learning mode: tag_id of newly scanned tag */
  newTagId?: string | null;
  playlists: Playlist[];
  tracks: Track[];
  streams: Stream[];
  onSave: (data: {
    name: string | null;
    content_type: ContentType;
    content_id: number;
  }) => void;
  onClose: () => void;
}

export const TagEditDialog: React.FC<TagEditDialogProps> = ({
  open,
  tag,
  newTagId,
  playlists,
  tracks,
  streams,
  onSave,
  onClose,
}) => {
  const { t } = useTranslation('rfid');

  const [name, setName] = useState<string>('');
  const [contentType, setContentType] = useState<ContentType>('playlist');
  const [contentId, setContentId] = useState<number | ''>('');

  useEffect(() => {
    if (tag) {
      setName(tag.name ?? '');
      setContentType(tag.content_type);
      setContentId(tag.content_id);
    } else {
      setName('');
      setContentType('playlist');
      setContentId('');
    }
  }, [tag, open]);

  const handleSave = () => {
    if (contentId === '') return;
    onSave({ name: name.trim() || null, content_type: contentType, content_id: contentId });
  };

  const isNewTag = !tag && !!newTagId;
  const title = isNewTag
    ? t('new_tag_dialog.title')
    : t('edit_tag');

  const contentOptions =
    contentType === 'playlist' ? playlists : contentType === 'stream' ? streams : tracks;
  const isValid = contentId !== '';

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ fontSize: '1.25rem', fontWeight: 600 }}>{title}</DialogTitle>
      <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: '16px !important' }}>
        {isNewTag && (
          <Typography variant="body2" color="text.secondary">
            {t('new_tag_dialog.subtitle', { tag_id: newTagId })}
          </Typography>
        )}

        <TextField
          label={t('new_tag_dialog.tag_name')}
          placeholder={t('new_tag_dialog.tag_name_placeholder')}
          value={name}
          onChange={(e) => setName(e.target.value)}
          fullWidth
          size="small"
        />

        <FormControl fullWidth size="small">
          <InputLabel>{t('new_tag_dialog.content_type')}</InputLabel>
          <Select
            value={contentType}
            label={t('new_tag_dialog.content_type')}
            onChange={(e) => {
              setContentType(e.target.value as ContentType);
              setContentId('');
            }}
          >
            <MenuItem value="playlist">{t('new_tag_dialog.content_type_playlist')}</MenuItem>
            <MenuItem value="track">{t('new_tag_dialog.content_type_track')}</MenuItem>
            <MenuItem value="stream">{t('new_tag_dialog.content_type_stream', { defaultValue: 'Stream' })}</MenuItem>
          </Select>
        </FormControl>

        <FormControl fullWidth size="small" required>
          <InputLabel>
            {contentType === 'playlist'
              ? t('new_tag_dialog.select_playlist')
              : contentType === 'stream'
                ? t('new_tag_dialog.select_stream', { defaultValue: 'Stream wählen' })
                : t('new_tag_dialog.select_track')}
          </InputLabel>
          <Select
            value={contentId}
            label={
              contentType === 'playlist'
                ? t('new_tag_dialog.select_playlist')
                : contentType === 'stream'
                  ? t('new_tag_dialog.select_stream', { defaultValue: 'Stream wählen' })
                  : t('new_tag_dialog.select_track')
            }
            onChange={(e) => setContentId(e.target.value as number)}
          >
            {contentOptions.map((item) => (
              <MenuItem key={item.id} value={item.id}>
                {'name' in item ? item.name : item.title}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>
          {t('cancel', { ns: 'common' })}
        </Button>
        <Button onClick={handleSave} variant="contained" disabled={!isValid}>
          {t('save', { ns: 'common' })}
        </Button>
      </DialogActions>
    </Dialog>
  );
};
