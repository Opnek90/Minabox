import React from 'react';
import { Box, Grid, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { TagCard } from './TagCard';
import type { Tag, Playlist, Podcast, Stream, Track } from '@/types/api';

interface TagListProps {
  tags: Tag[];
  playlists: Playlist[];
  tracks: Track[];
  streams: Stream[];
  podcasts: Podcast[];
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
  onEdit,
  onDelete,
  onToggleDisabled,
}) => {
  const { t } = useTranslation('rfid');

  const getContentName = (tag: Tag): string | null => {
    if (tag.content_type === 'playlist') {
      return playlists.find((p) => p.id === tag.content_id)?.name ?? null;
    }
    if (tag.content_type === 'stream') {
      return streams.find((s) => s.id === tag.content_id)?.title ?? null;
    }
    if (tag.content_type === 'podcast') {
      return podcasts.find((p) => p.id === tag.content_id)?.title ?? null;
    }
    return tracks.find((tr) => tr.id === tag.content_id)?.title ?? null;
  };

  if (tags.length === 0) {
    return (
      <Box display="flex" justifyContent="center" py={6}>
        <Typography color="text.secondary">{t('no_tags')}</Typography>
      </Box>
    );
  }

  return (
    <Grid container spacing={2}>
      {tags.map((tag) => (
        <Grid item xs={12} sm={6} md={4} key={tag.id}>
          <TagCard
            tag={tag}
            contentName={getContentName(tag)}
            onEdit={onEdit}
            onDelete={onDelete}
            onToggleDisabled={onToggleDisabled}
          />
        </Grid>
      ))}
    </Grid>
  );
};
