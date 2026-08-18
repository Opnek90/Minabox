import React, { useEffect, useMemo, useState } from 'react';
import {
  Autocomplete,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  FormControlLabel,
  FormLabel,
  Switch,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import type { Tag, ContentType, Playlist, Podcast, Stream, Track } from '@/types/api';
import { ActionButton } from '@/components/ui/ActionButton';
import { ResponsiveDialog } from '@/components/common/ResponsiveDialog';

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

  const contentTypes: { value: ContentType; label: string }[] = [
    { value: 'playlist', label: t('new_tag_dialog.content_type_playlist') },
    { value: 'track', label: t('new_tag_dialog.content_type_track') },
    { value: 'stream', label: t('new_tag_dialog.content_type_stream') },
    { value: 'podcast', label: t('new_tag_dialog.content_type_podcast') },
  ];

  const selectLabel =
    contentType === 'playlist'
      ? t('new_tag_dialog.select_playlist')
      : contentType === 'stream'
        ? t('new_tag_dialog.select_stream')
        : contentType === 'podcast'
          ? t('new_tag_dialog.select_podcast')
          : t('new_tag_dialog.select_track');

  // Auf einen flachen {id,label}-Typ normalisieren: Die vier Quellen haben
  // unterschiedliche Namensfelder (`name` vs. `title`), und die Autocomplete
  // filtert ueber genau dieses Label.
  const contentOptions = useMemo(() => {
    const source =
      contentType === 'playlist'
        ? playlists
        : contentType === 'stream'
          ? streams
          : contentType === 'podcast'
            ? podcasts
            : tracks;
    return source.map((item) => ({
      id: item.id,
      label: ('name' in item ? item.name : item.title) ?? String(item.id),
    }));
  }, [contentType, playlists, tracks, streams, podcasts]);

  const selectedOption = contentOptions.find((o) => o.id === contentId) ?? null;
  const isValid = contentId !== '';

  return (
    <ResponsiveDialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
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

        {/* Inhaltstyp als Segment-Leiste: vier kurze Labels, die nebeneinander
            passen – ein Tap statt Tap-Scroll-Tap durch ein Select-Popover. */}
        <FormControl fullWidth>
          <FormLabel sx={{ fontSize: '0.75rem', mb: 0.75 }}>
            {t('new_tag_dialog.content_type')}
          </FormLabel>
          <ToggleButtonGroup
            value={contentType}
            exclusive
            fullWidth
            size="small"
            onChange={(_, value: ContentType | null) => {
              if (!value) return;
              setContentType(value);
              setContentId('');
            }}
          >
            {contentTypes.map((ct) => (
              <ToggleButton key={ct.value} value={ct.value} sx={{ px: 0.5 }}>
                {ct.label}
              </ToggleButton>
            ))}
          </ToggleButtonGroup>
        </FormControl>

        {/* Autocomplete statt Select: Bei ein paar hundert Tracks ist ein
            Popover ohne Suchfeld auf dem Telefon nicht mehr bedienbar.
            `blurOnSelect` schliesst die Tastatur nach der Auswahl wieder. */}
        <Autocomplete
          options={contentOptions}
          value={selectedOption}
          onChange={(_, option) => setContentId(option ? option.id : '')}
          isOptionEqualToValue={(option, value) => option.id === value.id}
          getOptionLabel={(option) => option.label}
          autoHighlight
          blurOnSelect
          openOnFocus
          fullWidth
          noOptionsText={t('new_tag_dialog.no_options')}
          renderInput={(params) => (
            <TextField {...params} label={selectLabel} size="small" required />
          )}
        />

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
    </ResponsiveDialog>
  );
};
