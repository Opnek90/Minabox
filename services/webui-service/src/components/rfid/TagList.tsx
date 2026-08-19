import React from 'react';
import {
  Box,
  Chip,
  Divider,
  Grid,
  IconButton,
  List,
  ListItem,
  ListItemText,
  Tooltip,
  Typography,
} from '@mui/material';
import AccessTimeIcon from '@mui/icons-material/AccessTime';
import BlockIcon from '@mui/icons-material/Block';
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline';
import DeleteIcon from '@mui/icons-material/Delete';
import EditIcon from '@mui/icons-material/Edit';
import NfcIcon from '@mui/icons-material/Nfc';
import { useTranslation } from 'react-i18next';
import { TagCard } from './TagCard';
import type { Tag, Playlist, Podcast, Stream, Track } from '@/types/api';

// 3 Buttons à ~32px + Gaps = ~104px
const LIST_ITEM_PR = '112px';

function formatRelativeTime(isoString: string | null, locale: string): string | null {
  if (!isoString) return null;
  try {
    const diff = Date.now() - new Date(isoString).getTime();
    const rtf = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' });
    const units: [Intl.RelativeTimeFormatUnit, number][] = [
      ['minute', 60_000],
      ['hour', 3_600_000],
      ['day', 86_400_000],
      ['week', 604_800_000],
    ];
    for (let i = units.length - 1; i >= 0; i--) {
      const [unit, ms] = units[i];
      if (diff >= ms) return rtf.format(-Math.round(diff / ms), unit);
    }
    return rtf.format(-Math.round(diff / 60_000), 'minute');
  } catch {
    return null;
  }
}

interface TagListProps {
  tags: Tag[];
  playlists: Playlist[];
  tracks: Track[];
  streams: Stream[];
  podcasts: Podcast[];
  viewMode: 'card' | 'list';
  onEdit: (tag: Tag) => void;
  onDelete: (tag: Tag) => void;
  onToggleDisabled: (tag: Tag) => void;
}

export const TagList: React.FC<TagListProps> = ({
  tags,
  playlists,
  tracks,
  streams,
  podcasts,
  viewMode,
  onEdit,
  onDelete,
  onToggleDisabled,
}) => {
  const { t, i18n } = useTranslation('rfid');

  const getContentName = (tag: Tag): string | null => {
    if (tag.content_type === 'playlist') return playlists.find((p) => p.id === tag.content_id)?.name ?? null;
    if (tag.content_type === 'stream') return streams.find((s) => s.id === tag.content_id)?.title ?? null;
    if (tag.content_type === 'podcast') return podcasts.find((p) => p.id === tag.content_id)?.title ?? null;
    return tracks.find((tr) => tr.id === tag.content_id)?.title ?? null;
  };

  if (tags.length === 0) {
    return (
      <Box display="flex" justifyContent="center" py={6}>
        <Typography color="text.secondary">{t('no_tags')}</Typography>
      </Box>
    );
  }

  if (viewMode === 'list') {
    return (
      <List dense>
        {tags.map((tag, idx) => {
          const isDisabled = tag.disabled ?? false;
          const contentName = getContentName(tag);
          const relativeTime = formatRelativeTime(tag.last_scanned_at, i18n.language);
          return (
            <React.Fragment key={tag.id}>
              {idx > 0 && <Divider component="li" />}
              <ListItem
                secondaryAction={
                  <Box display="flex" alignItems="center">
                    <Tooltip title={isDisabled ? t('enable_tag') : t('disable_tag')}>
                      <IconButton size="small" color={isDisabled ? 'success' : 'warning'} onClick={() => onToggleDisabled(tag)}>
                        {isDisabled ? <CheckCircleOutlineIcon fontSize="small" /> : <BlockIcon fontSize="small" />}
                      </IconButton>
                    </Tooltip>
                    <Tooltip title={t('edit_tag')}>
                      <IconButton size="small" onClick={() => onEdit(tag)}><EditIcon fontSize="small" /></IconButton>
                    </Tooltip>
                    <Tooltip title={t('delete_tag')}>
                      <IconButton size="small" color="error" onClick={() => onDelete(tag)}><DeleteIcon fontSize="small" /></IconButton>
                    </Tooltip>
                  </Box>
                }
                sx={{
                  // pr verhindert Überlappung von Text und Buttons
                  pr: LIST_ITEM_PR,
                  borderLeft: isDisabled ? 4 : 0,
                  borderLeftColor: isDisabled ? 'error.main' : undefined,
                  bgcolor: isDisabled
                    ? (theme) => `color-mix(in srgb, ${theme.palette.error.main} 8%, ${theme.palette.background.paper})`
                    : undefined,
                  pl: isDisabled ? 1.5 : 2,
                }}
              >
                <Box mr={1.5} display="flex" alignItems="center">
                  <NfcIcon fontSize="small" color={isDisabled ? 'error' : 'primary'} />
                </Box>
                <ListItemText
                  primary={
                    <Box component="span" display="flex" alignItems="center" gap={1}>
                      <Typography component="span" variant="body2" fontWeight={600} noWrap>
                        {tag.name ?? tag.tag_id}
                      </Typography>
                      {isDisabled && (
                        <Chip label={t('tag_disabled_label')} size="small" color="error" variant="filled"
                          icon={<BlockIcon />} sx={{ height: 18, fontSize: '0.65rem', flexShrink: 0 }} />
                      )}
                    </Box>
                  }
                  secondary={
                    <Box component="span" display="flex" gap={1} alignItems="center" flexWrap="wrap">
                      <Typography component="span" variant="caption" color="text.secondary" noWrap>
                        {tag.tag_id}
                      </Typography>
                      {contentName && (
                        <Typography component="span" variant="caption" color="text.disabled" noWrap>
                          · {contentName}
                        </Typography>
                      )}
                      {relativeTime && (
                        <Box component="span" display="inline-flex" alignItems="center" gap={0.25} sx={{ flexShrink: 0 }}>
                          <AccessTimeIcon sx={{ fontSize: 10, color: 'text.disabled' }} />
                          <Typography component="span" variant="caption" color="text.disabled">
                            {relativeTime}
                          </Typography>
                        </Box>
                      )}
                    </Box>
                  }
                />
              </ListItem>
            </React.Fragment>
          );
        })}
      </List>
    );
  }

  return (
    <Grid container spacing={2}>
      {tags.map((tag) => (
        <Grid item xs={12} sm={6} lg={4} key={tag.id}>
          <TagCard tag={tag} contentName={getContentName(tag)}
            onEdit={onEdit} onDelete={onDelete} onToggleDisabled={onToggleDisabled} />
        </Grid>
      ))}
    </Grid>
  );
};
