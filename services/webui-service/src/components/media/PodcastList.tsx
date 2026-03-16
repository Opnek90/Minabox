import React, { useRef, useState } from 'react';
import {
  Box,
  Card,
  CardActions,
  CardContent,
  CardMedia,
  Chip,
  Divider,
  Grid,
  IconButton,
  InputAdornment,
  List,
  ListItem,
  ListItemText,
  Paper,
  Popover,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Tooltip,
  Typography,
  useMediaQuery,
  useTheme,
} from '@mui/material';
import ArrowDownwardIcon from '@mui/icons-material/ArrowDownward';
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward';
import DeleteIcon from '@mui/icons-material/Delete';
import EditIcon from '@mui/icons-material/Edit';
import FilterListIcon from '@mui/icons-material/FilterList';
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

const DEFAULT_SORT_KEY: SortKey = 'title';
const DEFAULT_SORT_DIR = 'asc' as const;

interface PodcastListProps {
  podcasts: Podcast[];
  onDelete: (podcast: Podcast) => void;
  onUpdate: (podcast: Podcast) => void;
  sortKey: string;
  sortDir: 'asc' | 'desc';
  onSortChange: (key: string, dir: 'asc' | 'desc') => void;
  viewMode: 'card' | 'list';
  onViewModeChange: (mode: 'card' | 'list') => void;
}

export const PodcastList: React.FC<PodcastListProps> = ({
  podcasts,
  onDelete,
  onUpdate,
  sortKey,
  sortDir,
  onSortChange,
  viewMode,
  onViewModeChange,
}) => {
  const { t } = useTranslation('media');
  const theme = useTheme();
  const isDesktop = useMediaQuery(theme.breakpoints.up('md'));
  const filterBtnRef = useRef<HTMLButtonElement>(null);
  const [popoverOpen, setPopoverOpen] = useState(false);
  const [search, setSearch] = useState('');
  const [podcastToEdit, setPodcastToEdit] = useState<Podcast | null>(null);

  const typedSortKey = sortKey as SortKey;

  const hasNonDefaultSort = typedSortKey !== DEFAULT_SORT_KEY || sortDir !== DEFAULT_SORT_DIR;

  const sortKeyLabel: Record<SortKey, string> = {
    title: t('podcasts.fields.title'),
    last_played_at: t('podcasts.fields.last_played'),
    last_fetched_at: t('podcasts.fields.last_fetched'),
  };

  const filtered = podcasts.filter((p) => {
    const q = search.toLowerCase();
    return p.title.toLowerCase().includes(q) || (p.description ?? '').toLowerCase().includes(q);
  });

  const sorted = [...filtered].sort((a, b) => {
    let aVal: string | number;
    let bVal: string | number;
    if (typedSortKey === 'last_fetched_at') {
      aVal = a.last_fetched_at ? new Date(a.last_fetched_at).getTime() : 0;
      bVal = b.last_fetched_at ? new Date(b.last_fetched_at).getTime() : 0;
    } else if (typedSortKey === 'last_played_at') {
      aVal = a.last_played_at ? new Date(a.last_played_at).getTime() : 0;
      bVal = b.last_played_at ? new Date(b.last_played_at).getTime() : 0;
    } else {
      aVal = a.title.toLowerCase(); bVal = b.title.toLowerCase();
    }
    if (aVal < bVal) return sortDir === 'asc' ? -1 : 1;
    if (aVal > bVal) return sortDir === 'asc' ? 1 : -1;
    return 0;
  });

  const handleSortKey = (_: React.MouseEvent, key: SortKey | null) => {
    if (!key) return;
    if (key === typedSortKey) onSortChange(key, sortDir === 'asc' ? 'desc' : 'asc');
    else onSortChange(key, 'asc');
  };

  const handleSortDirToggle = () =>
    onSortChange(typedSortKey, sortDir === 'asc' ? 'desc' : 'asc');

  const sortControls = (
    <Box display="flex" alignItems="center" gap={0.5}>
      <ToggleButtonGroup value={typedSortKey} exclusive onChange={handleSortKey} size="small">
        <ToggleButton value="title">{t('podcasts.fields.title')}</ToggleButton>
        <ToggleButton value="last_played_at">{t('podcasts.fields.last_played')}</ToggleButton>
        <ToggleButton value="last_fetched_at">{t('podcasts.fields.last_fetched')}</ToggleButton>
      </ToggleButtonGroup>
      <Tooltip title={sortDir === 'asc' ? t('podcasts.sort.asc') : t('podcasts.sort.desc')}>
        <IconButton size="small" onClick={handleSortDirToggle}>
          {sortDir === 'asc' ? <ArrowUpwardIcon fontSize="small" /> : <ArrowDownwardIcon fontSize="small" />}
        </IconButton>
      </Tooltip>
    </Box>
  );

  if (podcasts.length === 0) {
    return (
      <Box display="flex" justifyContent="center" py={6}>
        <Typography color="text.secondary">{t('podcasts.no_podcasts')}</Typography>
      </Box>
    );
  }

  return (
    <Box>
      {/* Toolbar */}
      <Box display="flex" gap={1} mb={1} alignItems="center">
        <ToggleButtonGroup value={viewMode} exclusive onChange={(_, v) => v && onViewModeChange(v)} size="small">
          <ToggleButton value="card" aria-label={t('view_mode_card')}><ViewModuleIcon fontSize="small" /></ToggleButton>
          <ToggleButton value="list" aria-label={t('view_mode_list')}><ViewListIcon fontSize="small" /></ToggleButton>
        </ToggleButtonGroup>

        <TextField
          placeholder={t('podcasts.search_placeholder')}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          size="small"
          InputProps={{ startAdornment: <InputAdornment position="start"><SearchIcon fontSize="small" /></InputAdornment> }}
          sx={{ flex: 1, minWidth: 0 }}
        />

        {isDesktop && sortControls}

        {!isDesktop && (
          <Tooltip title={t('podcasts.sort.open')}>
            <IconButton
              ref={filterBtnRef}
              size="small"
              onClick={() => setPopoverOpen(true)}
              aria-label={t('podcasts.sort.open')}
              sx={{
                position: 'relative',
                color: hasNonDefaultSort ? 'primary.main' : 'text.secondary',
                border: '1px solid',
                borderColor: hasNonDefaultSort ? 'primary.main' : 'divider',
                borderRadius: 1, px: 1,
              }}
            >
              <FilterListIcon fontSize="small" />
              {hasNonDefaultSort && (
                <Box component="span" sx={{
                  position: 'absolute', top: -6, right: -6,
                  width: 16, height: 16, borderRadius: '50%',
                  bgcolor: 'primary.main', color: 'primary.contrastText',
                  fontSize: '0.65rem', fontWeight: 700,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}>1</Box>
              )}
            </IconButton>
          </Tooltip>
        )}
      </Box>

      {/* Active Sort Chip */}
      {hasNonDefaultSort && (
        <Box display="flex" gap={0.75} flexWrap="wrap" mb={1.5} alignItems="center">
          <Chip size="small"
            icon={sortDir === 'asc' ? <ArrowUpwardIcon /> : <ArrowDownwardIcon />}
            label={sortKeyLabel[typedSortKey]}
            onDelete={() => onSortChange(DEFAULT_SORT_KEY, DEFAULT_SORT_DIR)}
            color="primary" variant="outlined" />
        </Box>
      )}

      {/* Mobile Popover */}
      <Popover
        open={popoverOpen && !isDesktop}
        anchorEl={filterBtnRef.current}
        onClose={() => setPopoverOpen(false)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        transformOrigin={{ vertical: 'top', horizontal: 'right' }}
        slotProps={{ paper: { sx: { mt: 0.5, borderRadius: 2, minWidth: 280 } } }}
      >
        <Paper sx={{ p: 2, display: 'flex', flexDirection: 'column', gap: 2 }}>
          <Box>
            <Typography variant="caption" color="text.secondary" fontWeight={600} display="block" mb={0.75}>
              {t('podcasts.sort.label')}
            </Typography>
            <Box display="flex" gap={1} alignItems="center">
              <ToggleButtonGroup value={typedSortKey} exclusive onChange={handleSortKey}
                size="small" sx={{ flex: 1, '& .MuiToggleButton-root': { flex: 1, fontSize: '0.78rem' } }}>
                <ToggleButton value="title">{t('podcasts.fields.title')}</ToggleButton>
                <ToggleButton value="last_played_at">{t('podcasts.fields.last_played')}</ToggleButton>
                <ToggleButton value="last_fetched_at">{t('podcasts.fields.last_fetched')}</ToggleButton>
              </ToggleButtonGroup>
              <Tooltip title={sortDir === 'asc' ? t('podcasts.sort.asc') : t('podcasts.sort.desc')}>
                <IconButton size="small" onClick={handleSortDirToggle}>
                  {sortDir === 'asc' ? <ArrowUpwardIcon fontSize="small" /> : <ArrowDownwardIcon fontSize="small" />}
                </IconButton>
              </Tooltip>
            </Box>
          </Box>
          {hasNonDefaultSort && (
            <>
              <Divider />
              <Box component="button" onClick={() => { onSortChange(DEFAULT_SORT_KEY, DEFAULT_SORT_DIR); setPopoverOpen(false); }}
                sx={{ background: 'none', border: 'none', cursor: 'pointer', color: 'text.secondary', fontSize: '0.8rem', textAlign: 'left', p: 0, '&:hover': { color: 'text.primary' } }}>
                {t('podcasts.sort.reset')}
              </Box>
            </>
          )}
        </Paper>
      </Popover>

      {/* Content */}
      {viewMode === 'card' ? (
        <Grid container spacing={2}>
          {sorted.map((podcast) => (
            <Grid item xs={12} sm={6} md={4} key={podcast.id}>
              <Card variant="outlined" sx={{ borderRadius: 2, height: '100%', display: 'flex', flexDirection: 'column' }}>
                {podcast.cover_art_url && (
                  <CardMedia component="img" height="120" image={podcast.cover_art_url} alt={podcast.title} sx={{ objectFit: 'cover' }} />
                )}
                <CardContent sx={{ pb: 0, flex: 1 }}>
                  <Typography variant="subtitle1" fontWeight={600} display="flex" alignItems="center" gap={1}>
                    <PodcastsIcon fontSize="small" color="primary" />{podcast.title}
                  </Typography>
                  {podcast.latest_episode_title && (
                    <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }} noWrap>
                      {t('podcasts.latest_episode')}: {podcast.latest_episode_title}
                    </Typography>
                  )}
                </CardContent>
                <CardActions sx={{ pt: 0 }}>
                  <Tooltip title={t('tracks.play')}>
                    <IconButton size="small" color="primary" onClick={() => audioApi.play({ podcast_id: podcast.id })}><PlayArrowIcon fontSize="small" /></IconButton>
                  </Tooltip>
                  <Tooltip title={t('podcasts.edit')}>
                    <IconButton size="small" onClick={() => setPodcastToEdit(podcast)}><EditIcon fontSize="small" /></IconButton>
                  </Tooltip>
                  <Tooltip title={t('tracks.delete')}>
                    <IconButton size="small" color="error" onClick={() => onDelete(podcast)}><DeleteIcon fontSize="small" /></IconButton>
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
                      <IconButton size="small" color="primary" onClick={() => audioApi.play({ podcast_id: podcast.id })}><PlayArrowIcon fontSize="small" /></IconButton>
                    </Tooltip>
                    <Tooltip title={t('podcasts.edit')}>
                      <IconButton size="small" onClick={() => setPodcastToEdit(podcast)}><EditIcon fontSize="small" /></IconButton>
                    </Tooltip>
                    <Tooltip title={t('tracks.delete')}>
                      <IconButton size="small" color="error" onClick={() => onDelete(podcast)}><DeleteIcon fontSize="small" /></IconButton>
                    </Tooltip>
                  </Box>
                }
              >
                {podcast.cover_art_url ? (
                  <Box component="img" src={podcast.cover_art_url} alt="" sx={{ width: 40, height: 40, objectFit: 'cover', borderRadius: 1, mr: 1 }} />
                ) : (
                  <Box mr={1} color="text.secondary"><PodcastsIcon fontSize="small" /></Box>
                )}
                <ListItemText
                  primary={podcast.title}
                  secondary={
                    podcast.latest_episode_title || podcast.last_played_at || podcast.last_fetched_at ? (
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
                                -Math.round((Date.now() - new Date(podcast.last_played_at).getTime()) / 60_000), 'minute'
                              )}
                            </Typography>
                          )}
                          {podcast.last_fetched_at && (
                            <Typography component="span" variant="caption" color="text.disabled">
                              {t('podcasts.last_fetched_label')}:{' '}
                              {new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' }).format(
                                -Math.round((Date.now() - new Date(podcast.last_fetched_at).getTime()) / 86_400_000), 'day'
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
        onSuccess={(updated) => { onUpdate(updated); setPodcastToEdit(null); }}
      />
    </Box>
  );
};
