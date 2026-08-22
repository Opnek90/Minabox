import React, { useRef, useState } from 'react';
import {
  Box,
  Card,
  CardActions,
  CardContent,
  CardMedia,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  Divider,
  Grid,
  IconButton,
  InputAdornment,
  List,
  ListItem,
  ListItemAvatar,
  ListItemText,
  Paper,
  Popover,
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
import FilterListIcon from '@mui/icons-material/FilterList';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import PlaylistPlayIcon from '@mui/icons-material/PlaylistPlay';
import QueueMusicIcon from '@mui/icons-material/QueueMusic';
import SearchIcon from '@mui/icons-material/Search';
import UploadIcon from '@mui/icons-material/Upload';
import ViewListIcon from '@mui/icons-material/ViewList';
import ViewModuleIcon from '@mui/icons-material/ViewModule';
import { useTranslation } from 'react-i18next';
import { useToast } from '@/contexts/ToastContext';
import type { Playlist, PlaylistDetail, Track } from '@/types/api';
import { playlistsApi } from '@/api/playlists';
import { audioApi } from '@/api/audio';
import { ActionButton } from '@/components/ui/ActionButton';
import { CoverUploadField } from './CoverUploadField';
import { PlaylistTracksDialog } from './PlaylistTracksDialog';
import { ResponsiveDialog } from '@/components/common/ResponsiveDialog';
import { useLayout } from '@/hooks/useLayout';

type SortKey = 'name' | 'track_count';
const DEFAULT_SORT_KEY: SortKey = 'name';
const DEFAULT_SORT_DIR = 'asc' as const;

// 5 Buttons à ~32px + Gaps = ~176px
const LIST_ITEM_PR = '180px';

interface PlaylistListProps {
  playlists: Playlist[];
  tracks: Track[];
  onUpdate: (playlist: Playlist) => void;
  onDelete: (playlist: Playlist) => void;
  onCreate: (playlist: Playlist) => void;
  viewMode: 'card' | 'list';
  onViewModeChange: (mode: 'card' | 'list') => void;
  sortKey: string;
  sortDir: 'asc' | 'desc';
  onSortChange: (key: string, dir: 'asc' | 'desc') => void;
  /** Wenn true, soll der Create-Dialog geöffnet werden. */
  createOpen: boolean;
  /** Wird aufgerufen sobald der Dialog geöffnet wurde, damit MediaPage den State zurücksetzen kann. */
  onCreateOpenHandled: () => void;
}

interface PlaylistFormData {
  name: string;
  description: string;
  coverFile: File | null;
}

export const PlaylistList: React.FC<PlaylistListProps> = ({
  playlists,
  tracks,
  onUpdate,
  onDelete,
  onCreate,
  viewMode,
  onViewModeChange,
  sortKey,
  sortDir,
  onSortChange,
  createOpen,
  onCreateOpenHandled,
}) => {
  const { t } = useTranslation('media');
  const { showSuccess, showError } = useToast();
  // Ab Tablet-Breite ist Platz fuer Sortierung, Filter und Zeilenaktionen
  // direkt in der Leiste; nur auf dem Handy wandern sie ins Popover bzw. in
  // ein Ueberlaufmenue. Vorher lag diese Grenze bei 900px, wodurch ein
  // 834px-Tablet die volle Handy-Bedienung bekam, obwohl die Breite reicht.
  const hasInlineControls = useLayout().hasRoomForInlineControls;
  const filterBtnRef = useRef<HTMLButtonElement>(null);
  const [popoverOpen, setPopoverOpen] = useState(false);
  const [search, setSearch] = useState('');

  const [formOpen, setFormOpen] = useState(false);
  const [editingPlaylist, setEditingPlaylist] = useState<Playlist | null>(null);
  const [formData, setFormData] = useState<PlaylistFormData>({ name: '', description: '', coverFile: null });
  const [deleteTarget, setDeleteTarget] = useState<Playlist | null>(null);
  const [loading, setLoading] = useState(false);
  const [tracksDialogPlaylist, setTracksDialogPlaylist] = useState<PlaylistDetail | null>(null);
  const coverInputRef = useRef<HTMLInputElement>(null);
  const [coverTargetId, setCoverTargetId] = useState<number | null>(null);

  // Öffne Create-Dialog wenn MediaPage den Button oben rechts drückt
  React.useEffect(() => {
    if (createOpen) {
      setEditingPlaylist(null);
      setFormData({ name: '', description: '', coverFile: null });
      setFormOpen(true);
      onCreateOpenHandled();
    }
  }, [createOpen, onCreateOpenHandled]);

  const typedSortKey = sortKey as SortKey;
  const hasNonDefaultSort = typedSortKey !== DEFAULT_SORT_KEY || sortDir !== DEFAULT_SORT_DIR;

  const sortKeyLabel: Record<SortKey, string> = {
    name: t('playlists.fields.name'),
    track_count: t('playlists.fields.track_count'),
  };

  const handleSortKey = (_: React.MouseEvent, key: SortKey | null) => {
    if (!key) return;
    if (key === typedSortKey) onSortChange(key, sortDir === 'asc' ? 'desc' : 'asc');
    else onSortChange(key, 'asc');
  };
  const handleSortDirToggle = () =>
    onSortChange(typedSortKey, sortDir === 'asc' ? 'desc' : 'asc');

  const filtered = playlists.filter((pl) =>
    pl.name.toLowerCase().includes(search.toLowerCase()) ||
    (pl.description ?? '').toLowerCase().includes(search.toLowerCase())
  );

  const sorted = [...filtered].sort((a, b) => {
    let aVal: string | number;
    let bVal: string | number;
    if (typedSortKey === 'track_count') {
      aVal = a.tracks?.length ?? 0;
      bVal = b.tracks?.length ?? 0;
    } else {
      aVal = a.name.toLowerCase();
      bVal = b.name.toLowerCase();
    }
    if (aVal < bVal) return sortDir === 'asc' ? -1 : 1;
    if (aVal > bVal) return sortDir === 'asc' ? 1 : -1;
    return 0;
  });

  const sortControls = (
    <Box display="flex" alignItems="center" gap={0.5}>
      <ToggleButtonGroup value={typedSortKey} exclusive onChange={handleSortKey} size="small">
        <ToggleButton value="name">{t('playlists.fields.name')}</ToggleButton>
        <ToggleButton value="track_count">{t('playlists.fields.track_count')}</ToggleButton>
      </ToggleButtonGroup>
      <Tooltip title={sortDir === 'asc' ? t('playlists.sort.asc') : t('playlists.sort.desc')}>
        <IconButton size="small" onClick={handleSortDirToggle}>
          {sortDir === 'asc' ? <ArrowUpwardIcon fontSize="small" /> : <ArrowDownwardIcon fontSize="small" />}
        </IconButton>
      </Tooltip>
    </Box>
  );

  // ── Dialog helpers ────────────────────────────────────────────────────────
  const handleOpenEdit = (pl: Playlist) => {
    setEditingPlaylist(pl);
    setFormData({ name: pl.name, description: pl.description ?? '', coverFile: null });
    setFormOpen(true);
  };

  const handleClearCoverInForm = () => setFormData((p) => ({ ...p, coverFile: null }));

  const handleRemoveCoverInForm = () => {
    if (formData.coverFile) { setFormData((p) => ({ ...p, coverFile: null })); return; }
    if (editingPlaylist?.cover_art_url) {
      playlistsApi.deleteCover(editingPlaylist.id)
        .then((updated) => { onUpdate(updated); setEditingPlaylist(updated); })
        .catch(() => showError(t('playlists.cover_remove_error')));
    }
  };

  const handleSave = async () => {
    if (!formData.name.trim()) return;
    setLoading(true);
    try {
      if (editingPlaylist) {
        let updated = await playlistsApi.update(editingPlaylist.id, {
          name: formData.name.trim(),
          description: formData.description.trim() || null,
        });
        if (formData.coverFile) updated = await playlistsApi.uploadCover(editingPlaylist.id, formData.coverFile);
        onUpdate(updated);
        showSuccess(t('playlists.updated'));
      } else {
        const created = await playlistsApi.create({
          name: formData.name.trim(),
          description: formData.description.trim() || null,
        });
        const withCover = formData.coverFile
          ? await playlistsApi.uploadCover(created.id, formData.coverFile)
          : created;
        onCreate(withCover);
        showSuccess(t('playlists.created'));
      }
      setFormOpen(false);
    } catch {
      showError(t('playlists.save_error'));
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteConfirm = async () => {
    if (!deleteTarget) return;
    try {
      await playlistsApi.delete(deleteTarget.id);
      onDelete(deleteTarget);
      showSuccess(t('playlists.deleted'));
    } catch {
      showError(t('playlists.delete_error'));
    } finally {
      setDeleteTarget(null);
    }
  };

  const handleOpenTracksDialog = async (pl: Playlist) => {
    try {
      const detail = await playlistsApi.getById(pl.id);
      setTracksDialogPlaylist(detail);
    } catch {
      showError(t('playlists.load_error'));
    }
  };

  const handleCoverUpload = async (file: File) => {
    if (coverTargetId === null) return;
    try {
      const updated = await playlistsApi.uploadCover(coverTargetId, file);
      onUpdate(updated);
      showSuccess(t('playlists.cover_uploaded'));
    } catch {
      showError(t('playlists.cover_upload_error'));
    } finally {
      setCoverTargetId(null);
    }
  };

  const handlePlay = (pl: Playlist) => {
    audioApi.play({ playlist_id: pl.id }).catch(() =>
      showError(t('playlists.play_error'))
    );
  };

  return (
    <Box>
      {/* Toolbar – identische Struktur wie TrackList/StreamList/PodcastList */}
      <Box display="flex" gap={1} mb={1} alignItems="center" flexWrap="wrap">
        <ToggleButtonGroup value={viewMode} exclusive onChange={(_, v) => v && onViewModeChange(v)} size="small">
          <ToggleButton value="card" aria-label={t('view_mode_card')}><ViewModuleIcon fontSize="small" /></ToggleButton>
          <ToggleButton value="list" aria-label={t('view_mode_list')}><ViewListIcon fontSize="small" /></ToggleButton>
        </ToggleButtonGroup>

        <TextField
          placeholder={t('playlists.search_placeholder')}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          size="small"
          InputProps={{ startAdornment: <InputAdornment position="start"><SearchIcon fontSize="small" /></InputAdornment> }}
          sx={{ flex: 1, minWidth: 0 }}
        />

        {hasInlineControls && sortControls}

        {!hasInlineControls && (
          <Tooltip title={t('playlists.sort.open')}>
            <IconButton
              ref={filterBtnRef}
              size="small"
              onClick={() => setPopoverOpen(true)}
              sx={{
                overflow: 'visible',
                color: hasNonDefaultSort ? 'primary.main' : 'text.secondary',
                border: '1px solid',
                borderColor: hasNonDefaultSort ? 'primary.main' : 'divider',
                borderRadius: 1,
                px: 1,
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
        open={popoverOpen && !hasInlineControls}
        anchorEl={filterBtnRef.current}
        onClose={() => setPopoverOpen(false)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        transformOrigin={{ vertical: 'top', horizontal: 'right' }}
        slotProps={{ paper: { sx: { mt: 0.5, borderRadius: 2, minWidth: 260 } } }}
      >
        <Paper sx={{ p: 2, display: 'flex', flexDirection: 'column', gap: 2 }}>
          <Box>
            <Typography variant="caption" color="text.secondary" fontWeight={600} display="block" mb={0.75}>
              {t('playlists.sort.label')}
            </Typography>
            <Box display="flex" gap={1} alignItems="center">
              <ToggleButtonGroup value={typedSortKey} exclusive onChange={handleSortKey}
                size="small" sx={{ flex: 1, '& .MuiToggleButton-root': { flex: 1, fontSize: '0.78rem' } }}>
                <ToggleButton value="name">{t('playlists.fields.name')}</ToggleButton>
                <ToggleButton value="track_count">{t('playlists.fields.track_count')}</ToggleButton>
              </ToggleButtonGroup>
              <Tooltip title={sortDir === 'asc' ? t('playlists.sort.asc') : t('playlists.sort.desc')}>
                <IconButton size="small" onClick={handleSortDirToggle}>
                  {sortDir === 'asc' ? <ArrowUpwardIcon fontSize="small" /> : <ArrowDownwardIcon fontSize="small" />}
                </IconButton>
              </Tooltip>
            </Box>
          </Box>
          {hasNonDefaultSort && (
            <>
              <Divider />
              <Box component="button"
                onClick={() => { onSortChange(DEFAULT_SORT_KEY, DEFAULT_SORT_DIR); setPopoverOpen(false); }}
                sx={{ background: 'none', border: 'none', cursor: 'pointer', color: 'text.secondary', fontSize: '0.8rem', textAlign: 'left', p: 0, '&:hover': { color: 'text.primary' } }}>
                {t('playlists.sort.reset')}
              </Box>
            </>
          )}
        </Paper>
      </Popover>

      {/* Content */}
      {sorted.length === 0 ? (
        <Box display="flex" justifyContent="center" py={6}>
          <Typography color="text.secondary">{t('playlists.no_playlists')}</Typography>
        </Box>
      ) : viewMode === 'list' ? (
        <List dense>
          {sorted.map((pl, idx) => (
            <React.Fragment key={pl.id}>
              {idx > 0 && <Divider component="li" />}
              <ListItem
                secondaryAction={
                  <Box display="flex" alignItems="center">
                    <Tooltip title={t('playlists.play')}>
                      <IconButton size="small" color="primary" onClick={() => handlePlay(pl)}><PlayArrowIcon fontSize="small" /></IconButton>
                    </Tooltip>
                    <Tooltip title={t('playlists.edit_tracks')}>
                      <IconButton size="small" onClick={() => handleOpenTracksDialog(pl)}><QueueMusicIcon fontSize="small" /></IconButton>
                    </Tooltip>
                    <Tooltip title={t('playlists.upload_cover')}>
                      <IconButton size="small" onClick={() => { setCoverTargetId(pl.id); coverInputRef.current?.click(); }}><UploadIcon fontSize="small" /></IconButton>
                    </Tooltip>
                    <Tooltip title={t('playlists.edit')}>
                      <IconButton size="small" onClick={() => handleOpenEdit(pl)}><EditIcon fontSize="small" /></IconButton>
                    </Tooltip>
                    <Tooltip title={t('playlists.delete')}>
                      <IconButton size="small" color="error" onClick={() => setDeleteTarget(pl)}><DeleteIcon fontSize="small" /></IconButton>
                    </Tooltip>
                  </Box>
                }
                sx={{ pr: LIST_ITEM_PR }}
              >
                <ListItemAvatar sx={{ minWidth: 52 }}>
                  {pl.cover_art_url ? (
                    <Box component="img" src={pl.cover_art_url} alt=""
                      sx={{ width: 40, height: 40, objectFit: 'cover', borderRadius: 1 }} />
                  ) : (
                    <Box sx={{ width: 40, height: 40, borderRadius: 1, bgcolor: 'action.hover', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                      <PlaylistPlayIcon sx={{ color: 'text.disabled', fontSize: 24 }} />
                    </Box>
                  )}
                </ListItemAvatar>
                <ListItemText
                  primary={pl.name}
                  secondary={
                    <Box component="span" display="flex" gap={1} alignItems="center">
                      {pl.description && <Typography component="span" variant="caption" noWrap>{pl.description}</Typography>}
                      {pl.tracks !== undefined && (
                        <Chip label={`${pl.tracks.length} ${t('playlists.track_count_label')}`}
                          size="small" variant="outlined" sx={{ height: 18, fontSize: '0.65rem', flexShrink: 0 }} />
                      )}
                    </Box>
                  }
                  primaryTypographyProps={{ fontWeight: 600, noWrap: true }}
                />
              </ListItem>
            </React.Fragment>
          ))}
        </List>
      ) : (
        <Grid container spacing={2}>
          {sorted.map((pl) => (
            <Grid item xs={12} sm={6} lg={4} key={pl.id}>
              <Card variant="outlined" sx={{ borderRadius: 2, height: '100%', display: 'flex', flexDirection: 'column' }}>
                {pl.cover_art_url && (
                  <CardMedia component="img" height="120" image={pl.cover_art_url} alt={pl.name} sx={{ objectFit: 'cover' }} />
                )}
                <CardContent sx={{ pb: 0, flex: 1 }}>
                  <Typography variant="subtitle1" fontWeight={600} display="flex" alignItems="center" gap={1}>
                    <PlaylistPlayIcon fontSize="small" color="primary" />
                    {pl.name}
                  </Typography>
                  {pl.description && (
                    <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }} noWrap>
                      {pl.description}
                    </Typography>
                  )}
                  {pl.tracks !== undefined && (
                    <Chip label={`${pl.tracks.length} ${t('playlists.track_count_label')}`}
                      size="small" variant="outlined" sx={{ mt: 1 }} />
                  )}
                </CardContent>
                <CardActions sx={{ pt: 0 }}>
                  <Tooltip title={t('playlists.play')}><IconButton size="small" color="primary" onClick={() => handlePlay(pl)}><PlayArrowIcon fontSize="small" /></IconButton></Tooltip>
                  <Tooltip title={t('playlists.edit_tracks')}><IconButton size="small" onClick={() => handleOpenTracksDialog(pl)}><QueueMusicIcon fontSize="small" /></IconButton></Tooltip>
                  <Tooltip title={t('playlists.upload_cover')}><IconButton size="small" onClick={() => { setCoverTargetId(pl.id); coverInputRef.current?.click(); }}><UploadIcon fontSize="small" /></IconButton></Tooltip>
                  <Tooltip title={t('playlists.edit')}><IconButton size="small" onClick={() => handleOpenEdit(pl)}><EditIcon fontSize="small" /></IconButton></Tooltip>
                  <Tooltip title={t('playlists.delete')}><IconButton size="small" color="error" onClick={() => setDeleteTarget(pl)}><DeleteIcon fontSize="small" /></IconButton></Tooltip>
                </CardActions>
              </Card>
            </Grid>
          ))}
        </Grid>
      )}

      {playlists.length > 0 && (
        <input ref={coverInputRef} type="file" accept="image/*" style={{ display: 'none' }}
          onChange={(e) => { const f = e.target.files?.[0]; if (f) handleCoverUpload(f); e.target.value = ''; }} />
      )}

      {/* Create / Edit Dialog */}
      <ResponsiveDialog open={formOpen} onClose={() => setFormOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle sx={{ fontSize: '1.25rem', fontWeight: 600 }}>
          {editingPlaylist ? t('playlists.edit') : t('playlists.create')}
        </DialogTitle>
        <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: '16px !important' }}>
          <CoverUploadField
            displayUrl={formData.coverFile ? URL.createObjectURL(formData.coverFile) : editingPlaylist?.cover_art_url ?? null}
            coverFile={formData.coverFile}
            onFileSelect={(file) => setFormData((p) => ({ ...p, coverFile: file }))}
            onRemove={editingPlaylist ? handleRemoveCoverInForm : handleClearCoverInForm}
          />
          <TextField label={t('playlists.fields.name')} placeholder={t('playlists.fields.name_placeholder')}
            value={formData.name} onChange={(e) => setFormData((p) => ({ ...p, name: e.target.value }))}
            fullWidth size="small" required />
          <TextField label={t('playlists.fields.description')} placeholder={t('playlists.fields.description_placeholder')}
            value={formData.description} onChange={(e) => setFormData((p) => ({ ...p, description: e.target.value }))}
            fullWidth size="small" multiline rows={2} />
        </DialogContent>
        <DialogActions>
          <ActionButton actionType="secondary" onClick={() => setFormOpen(false)}>{t('cancel', { ns: 'common' })}</ActionButton>
          <ActionButton actionType="primary" onClick={handleSave} disabled={!formData.name.trim() || loading}>
            {t('save', { ns: 'common' })}
          </ActionButton>
        </DialogActions>
      </ResponsiveDialog>

      <PlaylistTracksDialog
        open={!!tracksDialogPlaylist}
        playlist={tracksDialogPlaylist}
        allTracks={tracks}
        onClose={() => setTracksDialogPlaylist(null)}
        onSaved={(updated) => { onUpdate(updated); showSuccess(t('playlists.tracks_saved')); }}
      />

      <Dialog open={!!deleteTarget} onClose={() => setDeleteTarget(null)}>
        <DialogTitle sx={{ fontSize: '1.25rem', fontWeight: 600 }}>{t('playlists.delete')}</DialogTitle>
        <DialogContent>
          <DialogContentText>{t('playlists.delete_confirm', { name: deleteTarget?.name })}</DialogContentText>
        </DialogContent>
        <DialogActions>
          <ActionButton actionType="secondary" onClick={() => setDeleteTarget(null)}>{t('cancel', { ns: 'common' })}</ActionButton>
          <ActionButton actionType="destructive" onClick={handleDeleteConfirm}>{t('delete', { ns: 'common' })}</ActionButton>
        </DialogActions>
      </Dialog>
    </Box>
  );
};
