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
import SearchIcon from '@mui/icons-material/Search';
import StreamIcon from '@mui/icons-material/Stream';
import ViewListIcon from '@mui/icons-material/ViewList';
import ViewModuleIcon from '@mui/icons-material/ViewModule';
import { useTranslation } from 'react-i18next';
import { audioApi } from '@/api/audio';
import { StreamEditDialog } from '@/components/media/StreamEditDialog';
import type { Stream } from '@/types/api';

type SortKey = 'title' | 'artist' | 'last_played_at';

const DEFAULT_SORT_KEY: SortKey = 'title';
const DEFAULT_SORT_DIR = 'asc' as const;

// 3 Buttons (Play + Edit + Delete) à ~32px + Gaps = ~112px
const LIST_ITEM_PR = '112px';

interface StreamListProps {
  streams: Stream[];
  onDelete: (stream: Stream) => void;
  onUpdate: (stream: Stream) => void;
  sortKey: string;
  sortDir: 'asc' | 'desc';
  onSortChange: (key: string, dir: 'asc' | 'desc') => void;
  viewMode: 'card' | 'list';
  onViewModeChange: (mode: 'card' | 'list') => void;
}

export const StreamList: React.FC<StreamListProps> = ({
  streams,
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

  const typedSortKey = sortKey as SortKey;
  const [streamToEdit, setStreamToEdit] = useState<Stream | null>(null);

  const hasNonDefaultSort = typedSortKey !== DEFAULT_SORT_KEY || sortDir !== DEFAULT_SORT_DIR;

  const sortKeyLabel: Record<SortKey, string> = {
    title: t('streams.fields.title'),
    artist: t('streams.fields.artist'),
    last_played_at: t('streams.fields.last_played'),
  };

  const filtered = streams.filter((s) => {
    const q = search.toLowerCase();
    return s.title.toLowerCase().includes(q) || (s.artist ?? '').toLowerCase().includes(q);
  });

  const sorted = [...filtered].sort((a, b) => {
    let aVal: string | number;
    let bVal: string | number;
    if (typedSortKey === 'last_played_at') {
      aVal = a.last_played_at ? new Date(a.last_played_at).getTime() : 0;
      bVal = b.last_played_at ? new Date(b.last_played_at).getTime() : 0;
    } else if (typedSortKey === 'artist') {
      aVal = (a.artist ?? '').toLowerCase(); bVal = (b.artist ?? '').toLowerCase();
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
        <ToggleButton value="title">{t('streams.fields.title')}</ToggleButton>
        <ToggleButton value="artist">{t('streams.fields.artist')}</ToggleButton>
        <ToggleButton value="last_played_at">{t('streams.fields.last_played')}</ToggleButton>
      </ToggleButtonGroup>
      <Tooltip title={sortDir === 'asc' ? t('streams.sort.asc') : t('streams.sort.desc')}>
        <IconButton size="small" onClick={handleSortDirToggle}>
          {sortDir === 'asc' ? <ArrowUpwardIcon fontSize="small" /> : <ArrowDownwardIcon fontSize="small" />}
        </IconButton>
      </Tooltip>
    </Box>
  );

  if (streams.length === 0) {
    return (
      <Box display="flex" justifyContent="center" py={6}>
        <Typography color="text.secondary">{t('streams.no_streams')}</Typography>
      </Box>
    );
  }

  return (
    <Box>
      {/* Toolbar */}
      <Box display="flex" gap={1} mb={1} alignItems="center" flexWrap="wrap">
        <ToggleButtonGroup value={viewMode} exclusive onChange={(_, v) => v && onViewModeChange(v)} size="small">
          <ToggleButton value="card" aria-label={t('view_mode_card')}><ViewModuleIcon fontSize="small" /></ToggleButton>
          <ToggleButton value="list" aria-label={t('view_mode_list')}><ViewListIcon fontSize="small" /></ToggleButton>
        </ToggleButtonGroup>

        <TextField
          placeholder={t('streams.search_placeholder')}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          size="small"
          InputProps={{ startAdornment: <InputAdornment position="start"><SearchIcon fontSize="small" /></InputAdornment> }}
          sx={{ flex: 1, minWidth: 0 }}
        />

        {isDesktop && sortControls}

        {!isDesktop && (
          <Tooltip title={t('streams.sort.open')}>
            <IconButton
              ref={filterBtnRef}
              size="small"
              onClick={() => setPopoverOpen(true)}
              aria-label={t('streams.sort.open')}
              sx={{
                overflow: 'visible',
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
                  pointerEvents: 'none',
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
              {t('streams.sort.label')}
            </Typography>
            <Box display="flex" gap={1} alignItems="center">
              <ToggleButtonGroup value={typedSortKey} exclusive onChange={handleSortKey}
                size="small" sx={{ flex: 1, '& .MuiToggleButton-root': { flex: 1, fontSize: '0.78rem' } }}>
                <ToggleButton value="title">{t('streams.fields.title')}</ToggleButton>
                <ToggleButton value="artist">{t('streams.fields.artist')}</ToggleButton>
                <ToggleButton value="last_played_at">{t('streams.fields.last_played')}</ToggleButton>
              </ToggleButtonGroup>
              <Tooltip title={sortDir === 'asc' ? t('streams.sort.asc') : t('streams.sort.desc')}>
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
                {t('streams.sort.reset')}
              </Box>
            </>
          )}
        </Paper>
      </Popover>

      {/* Content */}
      {viewMode === 'card' ? (
        <Grid container spacing={2}>
          {sorted.map((stream) => (
            <Grid item xs={12} sm={6} md={4} key={stream.id}>
              <Card variant="outlined" sx={{ borderRadius: 2, height: '100%', display: 'flex', flexDirection: 'column' }}>
                {stream.cover_art_url && (
                  <CardMedia component="img" height="120" image={stream.cover_art_url} alt={stream.title} sx={{ objectFit: 'cover' }} />
                )}
                <CardContent sx={{ pb: 0, flex: 1 }}>
                  <Typography variant="subtitle1" fontWeight={600} display="flex" alignItems="center" gap={1}>
                    <StreamIcon fontSize="small" color="primary" />{stream.title}
                  </Typography>
                  {stream.artist && (
                    <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }} noWrap>{stream.artist}</Typography>
                  )}
                </CardContent>
                <CardActions sx={{ pt: 0 }}>
                  <Tooltip title={t('tracks.play')}>
                    <IconButton size="small" color="primary" onClick={() => audioApi.play({ stream_id: stream.id })}><PlayArrowIcon fontSize="small" /></IconButton>
                  </Tooltip>
                  <Tooltip title={t('streams.edit')}>
                    <IconButton size="small" onClick={() => setStreamToEdit(stream)}><EditIcon fontSize="small" /></IconButton>
                  </Tooltip>
                  <Tooltip title={t('tracks.delete')}>
                    <IconButton size="small" color="error" onClick={() => onDelete(stream)}><DeleteIcon fontSize="small" /></IconButton>
                  </Tooltip>
                </CardActions>
              </Card>
            </Grid>
          ))}
        </Grid>
      ) : (
        <List dense>
          {sorted.map((stream, idx) => (
            <React.Fragment key={stream.id}>
              {idx > 0 && <Divider component="li" />}
              <ListItem
                secondaryAction={
                  <Box display="flex" alignItems="center">
                    <Tooltip title={t('tracks.play')}>
                      <IconButton size="small" color="primary" onClick={() => audioApi.play({ stream_id: stream.id })}><PlayArrowIcon fontSize="small" /></IconButton>
                    </Tooltip>
                    <Tooltip title={t('streams.edit')}>
                      <IconButton size="small" onClick={() => setStreamToEdit(stream)}><EditIcon fontSize="small" /></IconButton>
                    </Tooltip>
                    <Tooltip title={t('tracks.delete')}>
                      <IconButton size="small" color="error" onClick={() => onDelete(stream)}><DeleteIcon fontSize="small" /></IconButton>
                    </Tooltip>
                  </Box>
                }
                sx={{ pr: LIST_ITEM_PR }}
              >
                {stream.cover_art_url ? (
                  <Box component="img" src={stream.cover_art_url} alt=""
                    sx={{ width: 40, height: 40, objectFit: 'cover', borderRadius: 1, mr: 1, flexShrink: 0 }} />
                ) : (
                  <Box mr={1} color="text.secondary" sx={{ flexShrink: 0 }}><StreamIcon fontSize="small" /></Box>
                )}
                <ListItemText
                  primary={stream.title}
                  primaryTypographyProps={{ noWrap: true }}
                  secondary={
                    <Box component="span" display="flex" gap={1} alignItems="center" flexWrap="wrap">
                      {stream.artist && <Typography component="span" variant="caption" noWrap>{stream.artist}</Typography>}
                      {stream.last_played_at && (
                        <Typography component="span" variant="caption" color="text.disabled" sx={{ flexShrink: 0 }}>
                          ·{' '}{new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' }).format(
                            -Math.round((Date.now() - new Date(stream.last_played_at).getTime()) / 3_600_000), 'hour'
                          )}
                        </Typography>
                      )}
                    </Box>
                  }
                />
              </ListItem>
            </React.Fragment>
          ))}
        </List>
      )}

      <StreamEditDialog
        open={!!streamToEdit}
        stream={streamToEdit}
        onClose={() => setStreamToEdit(null)}
        onSuccess={(updated) => { onUpdate(updated); setStreamToEdit(null); }}
      />
    </Box>
  );
};
