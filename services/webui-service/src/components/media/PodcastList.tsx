import React, { useState } from 'react';
import {
  Box,
  Card,
  CardActions,
  CardContent,
  CardMedia,
  Divider,
  Grid,
  IconButton,
  InputAdornment,
  List,
  ListItem,
  ListItemText,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Tooltip,
  Typography,
} from '@mui/material';
import ArrowDownwardIcon from '@mui/icons-material/ArrowDownward';
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward';
import DeleteIcon from '@mui/icons-material/Delete';
import EditIcon from '@mui/icons-material/Edit';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import PodcastsIcon from '@mui/icons-material/Podcasts';
import SearchIcon from '@mui/icons-material/Search';
import ViewListIcon from '@mui/icons-material/ViewList';
import ViewModuleIcon from '@mui/icons-material/ViewModule';
import { useTranslation } from 'react-i18next';
import { audioApi } from '@/api/audio';
import { PodcastEditDialog } from '@/components/media/PodcastEditDialog';
import type { Podcast } from '@/types/api';

type SortKey = 'title' | 'last_fetched_at' | 'last_played_at';

interface PodcastListProps {
  podcasts: Podcast[];
  onDelete: (podcast: Podcast) => void;
  onUpdate: (podcast: Podcast) => void;
}

export const PodcastList: React.FC<PodcastListProps> = ({ podcasts, onDelete, onUpdate }) => {
  const { t } = useTranslation('media');
  const [search, setSearch] = useState('');
  const [podcastToEdit, setPodcastToEdit] = useState<Podcast | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>('title');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');
  const [viewMode, setViewMode] = useState<'card' | 'list'>('list');

  const filtered = podcasts.filter((p) => {
    const q = search.toLowerCase();
    return (
      p.title.toLowerCase().includes(q) ||
      (p.description ?? '').toLowerCase().includes(q)
    );
  });

  const sorted = [...filtered].sort((a, b) => {
    let aVal: string | number;
    let bVal: string | number;
    if (sortKey === 'last_fetched_at') {
      aVal = a.last_fetched_at ? new Date(a.last_fetched_at).getTime() : 0;
      bVal = b.last_fetched_at ? new Date(b.last_fetched_at).getTime() : 0;
    } else if (sortKey === 'last_played_at') {
      aVal = a.last_played_at ? new Date(a.last_played_at).getTime() : 0;
      bVal = b.last_played_at ? new Date(b.last_played_at).getTime() : 0;
    } else {
      aVal = a.title.toLowerCase();
      bVal = b.title.toLowerCase();
    }
    if (aVal < bVal) return sortDir === 'asc' ? -1 : 1;
    if (aVal > bVal) return sortDir === 'asc' ? 1 : -1;
    return 0;
  });

  const handleSortKey = (_: React.MouseEvent, key: SortKey | null) => {
    if (!key) return;
    if (key === sortKey) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir('asc');
    }
  };

  if (podcasts.length === 0) {
    return (
      <Box display="flex" justifyContent="center" py={6}>
        <Typography color="text.secondary">{t('podcasts.no_podcasts')}</Typography>
      </Box>
    );
  }

  return (
    <Box>
      <Box display="flex" gap={2} mb={2} flexWrap="wrap" alignItems="center">
        <ToggleButtonGroup
          value={viewMode}
          exclusive
          onChange={(_, v) => v && setViewMode(v)}
          size="small"
        >
          <ToggleButton value="card" aria-label={t('view_mode_card')}>
            <ViewModuleIcon />
          </ToggleButton>
          <ToggleButton value="list" aria-label={t('view_mode_list')}>
            <ViewListIcon />
          </ToggleButton>
        </ToggleButtonGroup>
        <TextField
          placeholder={t('podcasts.search_placeholder')}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          size="small"
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon />
              </InputAdornment>
            ),
          }}
          sx={{ minWidth: 200 }}
        />

        <Box display="flex" alignItems="center" gap={0.5} ml="auto">
          <ToggleButtonGroup
            value={sortKey}
            exclusive
            onChange={handleSortKey}
            size="small"
          >
            <ToggleButton value="title">{t('podcasts.fields.title')}</ToggleButton>
            <ToggleButton value="last_played_at">{t('podcasts.fields.last_played')}</ToggleButton>
            <ToggleButton value="last_fetched_at">{t('podcasts.fields.last_fetched')}</ToggleButton>
          </ToggleButtonGroup>
          <Tooltip title={t(`podcasts.sort.${sortDir}`)}>
            <IconButton
              size="small"
              onClick={() => setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))}
            >
              {sortDir === 'asc' ? (
                <ArrowUpwardIcon fontSize="small" />
              ) : (
                <ArrowDownwardIcon fontSize="small" />
              )}
            </IconButton>
          </Tooltip>
        </Box>
      </Box>

      {viewMode === 'card' ? (
        <Grid container spacing={2}>
          {sorted.map((podcast) => (
            <Grid item xs={12} sm={6} md={4} key={podcast.id}>
              <Card
                variant="outlined"
                sx={{ borderRadius: 2, height: '100%', display: 'flex', flexDirection: 'column' }}
              >
                {podcast.cover_art_url && (
                  <CardMedia
                    component="img"
                    height="120"
                    image={podcast.cover_art_url}
                    alt={podcast.title}
                    sx={{ objectFit: 'cover' }}
                  />
                )}
                <CardContent sx={{ pb: 0, flex: 1 }}>
                  <Typography variant="subtitle1" fontWeight={600} display="flex" alignItems="center" gap={1}>
                    <PodcastsIcon fontSize="small" color="primary" />
                    {podcast.title}
                  </Typography>
                  {podcast.latest_episode_title && (
                    <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }} noWrap>
                      {t('podcasts.latest_episode')}: {podcast.latest_episode_title}
                    </Typography>
                  )}
                </CardContent>
                <CardActions sx={{ pt: 0 }}>
                  <Tooltip title={t('tracks.play')}>
                    <IconButton size="small" color="primary" onClick={() => audioApi.play({ podcast_id: podcast.id })}>
                      <PlayArrowIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title={t('podcasts.edit', { defaultValue: 'Bearbeiten' })}>
                    <IconButton size="small" onClick={() => setPodcastToEdit(podcast)}>
                      <EditIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title={t('tracks.delete')}>
                    <IconButton size="small" color="error" onClick={() => onDelete(podcast)}>
                      <DeleteIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </CardActions>
              </Card>
            </Grid>
          ))}
        </Grid>
      ) : (
      <List dense>
        {sorted.map((podcast, idx) => (
          <React.Fragment key={podcast.id}>
            {idx > 0 && <Divider component="li" />}
            <ListItem
              secondaryAction={
                <Box>
                  <Tooltip title={t('tracks.play')}>
                    <IconButton
                      size="small"
                      color="primary"
                      onClick={() => audioApi.play({ podcast_id: podcast.id })}
                    >
                      <PlayArrowIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title={t('podcasts.edit', { defaultValue: 'Bearbeiten' })}>
                    <IconButton size="small" onClick={() => setPodcastToEdit(podcast)}>
                      <EditIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title={t('tracks.delete')}>
                    <IconButton
                      size="small"
                      color="error"
                      onClick={() => onDelete(podcast)}
                    >
                      <DeleteIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </Box>
              }
            >
              {podcast.cover_art_url ? (
                <Box
                  component="img"
                  src={podcast.cover_art_url}
                  alt=""
                  sx={{ width: 40, height: 40, objectFit: 'cover', borderRadius: 1, mr: 1 }}
                />
              ) : (
                <Box mr={1} color="text.secondary">
                  <PodcastsIcon fontSize="small" />
                </Box>
              )}
              <ListItemText
              primary={podcast.title}
              secondary={
                podcast.latest_episode_title ||
                podcast.last_played_at ||
                podcast.last_fetched_at ? (
                  <Box component="span" display="flex" flexDirection="column" gap={0.25}>
                    {podcast.latest_episode_title && (
                      <Typography component="span" variant="caption" display="block">
                        {t('podcasts.latest_episode')}: {podcast.latest_episode_title}
                        {podcast.latest_episode_published_at &&
                          ` (${new Date(podcast.latest_episode_published_at).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })})`}
                      </Typography>
                    )}
                    <Box component="span" display="flex" gap={1} flexWrap="wrap" alignItems="center">
                      {podcast.last_played_at && (
                        <Typography component="span" variant="caption" color="text.disabled">
                          {t('podcasts.last_played')}:{' '}
                          {new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' }).format(
                            -Math.round(
                              (Date.now() - new Date(podcast.last_played_at).getTime()) / 60_000
                            ),
                            'minute'
                          )}
                        </Typography>
                      )}
                      {podcast.last_fetched_at && (
                        <Typography component="span" variant="caption" color="text.disabled">
                          {t('podcasts.last_fetched_label')}:{' '}
                          {new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' }).format(
                            -Math.round(
                              (Date.now() - new Date(podcast.last_fetched_at).getTime()) /
                                86_400_000
                            ),
                            'day'
                          )}
                        </Typography>
                      )}
                    </Box>
                  </Box>
                ) : null
              }
            />
          </ListItem>
          </React.Fragment>
        ))}
      </List>
      )}

      <PodcastEditDialog
        open={!!podcastToEdit}
        podcast={podcastToEdit}
        onClose={() => setPodcastToEdit(null)}
        onSuccess={(updated) => {
          onUpdate(updated);
          setPodcastToEdit(null);
        }}
      />
    </Box>
  );
};
