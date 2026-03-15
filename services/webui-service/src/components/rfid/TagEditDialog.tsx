import React, { useEffect, useState } from 'react';
import {
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  FormControlLabel,
  InputLabel,
  MenuItem,
  Select,
  Switch,
  TextField,
  Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import type { Tag, ContentType, Playlist, Podcast, Stream, Track } from '@/types/api';
import { ActionButton } from '@/components/ui/ActionButton';

interface TagEditDialogProps {
  open: boolean;
  tag: Tag | null;
  newTagId?: string | null;
  playlists: Playlist[];
  tracks: Track[];
  streams: Stream[];
  podcasts: Podcast[];
  onSave: (data: {
    name: string | null;
    content_type: ContentType;
    content_id: number;
    disabled: boolean;
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
  podcasts,
  onSave,
  onClose,
}) => {
  const { t } = useTranslation('rfid');

  const [name, setName] = useState<string>('');
  const [contentType, setContentType] = useState<ContentType>('playlist');
  const [contentId, setContentId] = useState<number | ''>('');
  const [disabled, setDisabled] = useState<boolean>(false);

  useEffect(() => {
    if (tag) {
      setName(tag.name ?? '');
      setContentType(tag.content_type);
      setContentId(tag.content_id);
      setDisabled(tag.disabled ?? false);
    } else {
      setName('');
      setContentType('playlist');
      setContentId('');
      setDisabled(false);
    }
  }, [tag, open]);

  const handleSave = () => {
    if (contentId === '') return;
    onSave({ name: name.trim() || null, content_type: contentType, content_id: contentId, disabled });
  };

  const isNewTag = !tag && !!newTagId;
  const title = isNewTag ? t('new_tag_dialog.title') : t('edit_tag');

  const contentOptions =
    contentType === 'playlist'
      ? playlists
      : contentType === 'stream'
        ? streams
        : contentType === 'podcast'
          ? podcasts
          : tracks;
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
            <MenuItem value="stream">{t('new_tag_dialog.content_type_stream')}</MenuItem>
            <MenuItem value="podcast">{t('new_tag_dialog.content_type_podcast')}</MenuItem>
          </Select>
        </FormControl>

        <FormControl fullWidth size="small" required>
          <InputLabel>
            {contentType === 'playlist'
              ? t('new_tag_dialog.select_playlist')
              : contentType === 'stream'
                ? t('new_tag_dialog.select_stream')
                : contentType === 'podcast'
                  ? t('new_tag_dialog.select_podcast')
                  : t('new_tag_dialog.select_track')}
          </InputLabel>
          <Select
            value={contentId}
            label={
              contentType === 'playlist'
                ? t('new_tag_dialog.select_playlist')
                : contentType === 'stream'
                  ? t('new_tag_dialog.select_stream')
                  : contentType === 'podcast'
                    ? t('new_tag_dialog.select_podcast')
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

        <FormControlLabel
          control={
            <Switch
              checked={disabled}
              onChange={(e) => setDisabled(e.target.checked)}
              color="warning"
            />
          }
          label={t('disable_tag_label')}
        />
      </DialogContent>
      <DialogActions>
        <ActionButton actionType="secondary" onClick={onClose}>
          {t('cancel', { ns: 'common' })}
        </ActionButton>
        <ActionButton actionType="primary" onClick={handleSave} disabled={!isValid}>
          {t('save', { ns: 'common' })}
        </ActionButton>
      </DialogActions>
    </Dialog>
  );
};
