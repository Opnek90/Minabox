import React, { useState } from 'react';
import { Box, Typography } from '@mui/material';
import DeleteIcon from '@mui/icons-material/Delete';
import EditIcon from '@mui/icons-material/Edit';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import StreamIcon from '@mui/icons-material/Stream';
import { useTranslation } from 'react-i18next';
import { audioApi } from '@/api/audio';
import { LastPlayedCaption } from '@/components/media/LastPlayedCaption';
import { StreamEditDialog } from '@/components/media/StreamEditDialog';
import { CollectionView, type CollectionDescriptor } from './CollectionView';
import { RelativeTimeCell } from './RelativeTimeCell';
import type { MediaFolder } from './FolderTree';
import type { Stream } from '@/types/api';
import type { ViewMode } from '@/contexts/UserPrefsContext';
import { timeValue } from '@/utils/sortValue';

/** MIME type used for DnD transfer of a stream ID */
const STREAM_DRAG_TYPE = 'application/minabox-stream-id';

interface StreamListProps {
  streams: Stream[];
  folders: MediaFolder[];
  currentFolderId: number | null;
  onNavigateFolder: (folderId: number | null) => void;
  onFolderCreate: (name: string, parentId: number | null) => Promise<void>;
  onFolderRename: (folder: MediaFolder, name: string) => Promise<void>;
  onFolderDelete: (folder: MediaFolder) => Promise<void>;
  onMoveStreamToFolder: (stream: Stream, folderId: number | null) => Promise<void>;
  onDelete: (stream: Stream) => void;
  onUpdate: (stream: Stream) => void;
  sortKey: string;
  sortDir: 'asc' | 'desc';
  onSortChange: (key: string, dir: 'asc' | 'desc') => void;
  viewMode: ViewMode;
  onViewModeChange: (mode: ViewMode) => void;
  treeCollapsed?: boolean;
  onTreeCollapsedChange?: (collapsed: boolean) => void;
  pageSize?: number;
  onPageSizeChange?: (size: number) => void;
  onRegisterCreateFolder?: (fn: () => void) => void;
}

export const StreamList: React.FC<StreamListProps> = ({
  streams,
  onDelete,
  onUpdate,
  onMoveStreamToFolder,
  ...viewProps
}) => {
  const { t } = useTranslation('media');
  const [streamToEdit, setStreamToEdit] = useState<Stream | null>(null);

  const thumbnail = (stream: Stream, size: number) =>
    stream.cover_art_url ? (
      <Box
        component="img"
        src={stream.cover_art_url}
        alt=""
        sx={{ width: size, height: size, objectFit: 'cover', borderRadius: size > 28 ? 1 : 0.5, display: 'block' }}
      />
    ) : (
      <Box color="text.secondary" sx={{ display: 'flex' }}>
        <StreamIcon fontSize="small" />
      </Box>
    );

  const descriptor: CollectionDescriptor<Stream> = {
    dragType: STREAM_DRAG_TYPE,
    treeLabel: t('tabs.streams'),
    searchPlaceholder: t('streams.search_placeholder'),
    emptyText: t('streams.no_streams'),
    sortLabel: t('streams.sort.label'),
    sortOpenLabel: t('streams.sort.open'),
    sortAscLabel: t('streams.sort.asc'),
    sortDescLabel: t('streams.sort.desc'),
    resetLabel: t('streams.sort.reset'),
    defaultSortKey: 'title',
    sortOptions: [
      { key: 'title', label: t('streams.fields.title'), value: (s) => s.title.toLowerCase() },
      { key: 'artist', label: t('streams.fields.artist'), value: (s) => (s.artist ?? '').toLowerCase() },
      { key: 'last_played_at', label: t('streams.fields.last_played'), value: (s) => timeValue(s.last_played_at) },
    ],
    searchFields: (s) => [s.title, s.artist],
    renderThumbnail: thumbnail,
    renderIcon: () => <StreamIcon fontSize="small" color="primary" />,
    renderCardBody: (s) => (
      <>
        {s.artist && (
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }} noWrap>{s.artist}</Typography>
        )}
        <Box sx={{ mt: 1 }}>
          <LastPlayedCaption
            value={s.last_played_at}
            label={t('streams.fields.last_played')}
            emptyLabel={t('never_played')}
          />
        </Box>
      </>
    ),
    renderListSecondary: (s) => (
      <Box component="span" display="flex" gap={1} alignItems="center" flexWrap="wrap">
        {s.artist && <Typography component="span" variant="caption" noWrap>{s.artist}</Typography>}
        <LastPlayedCaption
          value={s.last_played_at}
          label={t('streams.fields.last_played')}
          emptyLabel={t('never_played')}
          separator={Boolean(s.artist)}
        />
      </Box>
    ),
    columns: [
      { key: 'cover', label: '', width: 44, render: (s) => thumbnail(s, 28) },
      { key: 'title', label: t('streams.fields.title'), sortable: true, width: '38%', render: (s) => s.title },
      { key: 'artist', label: t('streams.fields.artist'), sortable: true, width: '32%', render: (s) => s.artist || '—' },
      {
        key: 'last_played_at',
        label: t('streams.fields.last_played'),
        sortable: true,
        render: (s) => <RelativeTimeCell value={s.last_played_at} />,
      },
    ],
    actions: [
      {
        key: 'play',
        label: t('tracks.play'),
        icon: <PlayArrowIcon fontSize="small" />,
        primary: true,
        onClick: (s) => audioApi.play({ stream_id: s.id }),
      },
      {
        key: 'edit',
        label: t('streams.edit'),
        icon: <EditIcon fontSize="small" />,
        onClick: (s) => setStreamToEdit(s),
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
      <CollectionView<Stream>
        {...viewProps}
        items={streams}
        onMoveToFolder={onMoveStreamToFolder}
        descriptor={descriptor}
      />

      {/* onChanged rather than onSaved when the cover is removed: refresh the
          list, but the open dialog too - otherwise it kept showing the deleted
          image. */}
      <StreamEditDialog
        open={!!streamToEdit}
        stream={streamToEdit}
        onClose={() => setStreamToEdit(null)}
        onSaved={(updated) => { onUpdate(updated); setStreamToEdit(null); }}
        onChanged={(updated) => { onUpdate(updated); setStreamToEdit(updated); }}
      />
    </>
  );
};
