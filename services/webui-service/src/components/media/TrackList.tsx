import React, { useState } from 'react';
import { Avatar, Box, Chip, Typography } from '@mui/material';
import AudiotrackIcon from '@mui/icons-material/Audiotrack';
import DeleteIcon from '@mui/icons-material/Delete';
import EditIcon from '@mui/icons-material/Edit';
import LinkIcon from '@mui/icons-material/Link';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import PlaylistAddIcon from '@mui/icons-material/PlaylistAdd';
import { useTranslation } from 'react-i18next';
import { audioApi } from '@/api/audio';
import type { Playlist, Track } from '@/types/api';
import type { ViewMode } from '@/contexts/UserPrefsContext';
import { formatTime } from '@/utils/formatTime';
import { timeValue } from '@/utils/sortValue';
import { AddToPlaylistDialog } from './AddToPlaylistDialog';
import { CollectionView, type CollectionDescriptor } from './CollectionView';
import { LastPlayedCaption } from './LastPlayedCaption';
import { RelativeTimeCell } from './RelativeTimeCell';
import type { MediaFolder } from './FolderTree';

/** MIME type used for DnD transfer of a track ID */
const TRACK_DRAG_TYPE = 'application/minabox-track-id';

interface TrackListProps {
  tracks: Track[];
  folders: MediaFolder[];
  playlists: Playlist[];
  currentFolderId: number | null;
  onNavigateFolder: (folderId: number | null) => void;
  onFolderCreate: (name: string, parentId: number | null) => Promise<void>;
  onFolderRename: (folder: MediaFolder, name: string) => Promise<void>;
  onFolderDelete: (folder: MediaFolder) => Promise<void>;
  onMoveTrackToFolder: (track: Track, folderId: number | null) => Promise<void>;
  onDelete: (track: Track) => void;
  onEdit?: (track: Track) => void;
  sortKey: string;
  sortDir: 'asc' | 'desc';
  onSortChange: (key: string, dir: 'asc' | 'desc') => void;
  viewMode: ViewMode;
  onViewModeChange: (mode: ViewMode) => void;
  filter: string;
  onFilterChange: (filter: string) => void;
  treeCollapsed?: boolean;
  onTreeCollapsedChange?: (collapsed: boolean) => void;
  pageSize?: number;
  onPageSizeChange?: (size: number) => void;
  onRegisterCreateFolder?: (fn: () => void) => void;
  onPlaylistUpdated?: (playlist: Playlist) => void;
}

export const TrackList: React.FC<TrackListProps> = ({
  tracks,
  playlists,
  onDelete,
  onEdit,
  onMoveTrackToFolder,
  filter,
  onFilterChange,
  onPlaylistUpdated,
  ...viewProps
}) => {
  const { t } = useTranslation('media');
  const [addToPlaylistTrack, setAddToPlaylistTrack] = useState<Track | null>(null);

  const thumbnail = (track: Track, size: number) =>
    track.cover_art_url ? (
      <Avatar src={track.cover_art_url} variant="rounded" sx={{ width: size, height: size }}>
        <AudiotrackIcon fontSize="small" />
      </Avatar>
    ) : (
      <Avatar variant="rounded" sx={{ width: size, height: size, bgcolor: 'action.selected' }}>
        {track.source_type === 'remote' ? <LinkIcon fontSize="small" /> : <AudiotrackIcon fontSize="small" />}
      </Avatar>
    );

  const descriptor: CollectionDescriptor<Track> = {
    dragType: TRACK_DRAG_TYPE,
    treeLabel: t('tabs.tracks'),
    searchPlaceholder: t('track_selector.search_placeholder'),
    emptyText: t('tracks.no_tracks'),
    sortLabel: t('tracks.sort.label'),
    sortOpenLabel: t('tracks.filter.open'),
    sortAscLabel: t('tracks.sort.asc'),
    sortDescLabel: t('tracks.sort.desc'),
    resetLabel: t('tracks.filter.reset_all'),
    defaultSortKey: 'title',
    sortOptions: [
      { key: 'title', label: t('tracks.fields.title'), value: (tr) => tr.title.toLowerCase() },
      { key: 'artist', label: t('tracks.fields.artist'), value: (tr) => (tr.artist ?? '').toLowerCase() },
      { key: 'duration_ms', label: t('tracks.fields.duration'), value: (tr) => tr.duration_ms ?? 0 },
      { key: 'last_played_at', label: t('tracks.fields.last_played'), value: (tr) => timeValue(tr.last_played_at) },
    ],
    searchFields: (tr) => [tr.title, tr.artist, tr.album],
    filter: {
      value: filter,
      defaultValue: 'all',
      onChange: onFilterChange,
      label: t('tracks.filter.label'),
      options: [
        { value: 'all', label: t('tracks.filter.all') },
        { value: 'file', label: t('tracks.filter.files') },
        { value: 'remote', label: t('tracks.filter.remote') },
      ],
      matches: (tr, value) => value === 'all' || tr.source_type === value,
    },
    renderThumbnail: thumbnail,
    renderIcon: (tr) =>
      tr.source_type === 'remote'
        ? <LinkIcon fontSize="small" color="primary" />
        : <AudiotrackIcon fontSize="small" color="primary" />,
    renderCardBody: (tr) => (
      <>
        {(tr.artist || tr.album) && (
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }} noWrap>
            {[tr.artist, tr.album].filter(Boolean).join(' · ')}
          </Typography>
        )}
        <Box display="flex" alignItems="center" gap={1} flexWrap="wrap" sx={{ mt: 1 }}>
          {tr.duration_ms != null && (
            <Chip label={formatTime(tr.duration_ms)} size="small" variant="outlined" />
          )}
          <LastPlayedCaption
            value={tr.last_played_at}
            label={t('tracks.fields.last_played')}
            emptyLabel={t('never_played')}
            separator={tr.duration_ms != null}
          />
        </Box>
      </>
    ),
    renderListSecondary: (tr) => (
      <Box component="span" display="flex" gap={1} alignItems="center" flexWrap="wrap">
        {tr.artist && <Typography component="span" variant="caption" noWrap>{tr.artist}</Typography>}
        {tr.album && <Typography component="span" variant="caption" color="text.secondary" noWrap>· {tr.album}</Typography>}
        {tr.duration_ms != null && (
          <Chip label={formatTime(tr.duration_ms)} size="small" variant="outlined"
            sx={{ height: 18, fontSize: '0.65rem', flexShrink: 0 }} />
        )}
        <LastPlayedCaption
          value={tr.last_played_at}
          label={t('tracks.fields.last_played')}
          emptyLabel={t('never_played')}
          separator
        />
      </Box>
    ),
    columns: [
      { key: 'cover', label: '', width: 44, render: (tr) => thumbnail(tr, 28) },
      { key: 'title', label: t('tracks.fields.title'), sortable: true, width: '26%', render: (tr) => tr.title },
      { key: 'artist', label: t('tracks.fields.artist'), sortable: true, width: '20%', render: (tr) => tr.artist || '—' },
      { key: 'album', label: t('tracks.fields.album'), width: '20%', render: (tr) => tr.album || '—' },
      {
        key: 'duration_ms',
        label: t('tracks.fields.duration'),
        sortable: true,
        numeric: true,
        width: 96,
        render: (tr) => (tr.duration_ms != null ? formatTime(tr.duration_ms) : '—'),
      },
      {
        key: 'last_played_at',
        label: t('tracks.fields.last_played'),
        sortable: true,
        render: (tr) => <RelativeTimeCell value={tr.last_played_at} />,
      },
    ],
    actions: [
      {
        key: 'play',
        label: t('tracks.play'),
        icon: <PlayArrowIcon fontSize="small" />,
        primary: true,
        onClick: (tr) => audioApi.play({ track_id: tr.id }),
      },
      {
        key: 'playlist',
        label: t('playlists.add_to_playlist'),
        icon: <PlaylistAddIcon fontSize="small" />,
        available: playlists.length > 0,
        onClick: (tr) => setAddToPlaylistTrack(tr),
      },
      {
        key: 'edit',
        label: t('tracks.edit'),
        icon: <EditIcon fontSize="small" />,
        available: Boolean(onEdit),
        onClick: (tr) => onEdit?.(tr),
      },
      {
        key: 'delete',
        label: t('tracks.delete'),
        icon: <DeleteIcon fontSize="small" />,
        destructive: true,
        onClick: onDelete,
      },
    ],
  };

  return (
    <>
      <CollectionView<Track>
        {...viewProps}
        items={tracks}
        onMoveToFolder={onMoveTrackToFolder}
        descriptor={descriptor}
      />

      <AddToPlaylistDialog
        open={!!addToPlaylistTrack}
        track={addToPlaylistTrack}
        playlists={playlists}
        onClose={() => setAddToPlaylistTrack(null)}
        onAdded={(pl) => onPlaylistUpdated?.(pl)}
      />
    </>
  );
};
