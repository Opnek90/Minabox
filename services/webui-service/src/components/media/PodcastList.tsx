import React, { useState } from 'react';
import { Box, Typography } from '@mui/material';
import DeleteIcon from '@mui/icons-material/Delete';
import EditIcon from '@mui/icons-material/Edit';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import PodcastsIcon from '@mui/icons-material/Podcasts';
import { useTranslation } from 'react-i18next';
import { audioApi } from '@/api/audio';
import { LastPlayedCaption } from '@/components/media/LastPlayedCaption';
import { PodcastEditDialog } from '@/components/media/PodcastEditDialog';
import { CollectionView, type CollectionDescriptor } from './CollectionView';
import { RelativeTimeCell } from './RelativeTimeCell';
import type { MediaFolder } from './FolderTree';
import type { Podcast } from '@/types/api';
import type { ViewMode } from '@/contexts/UserPrefsContext';
import { timeValue } from '@/utils/sortValue';

/** MIME type used for DnD transfer of a podcast ID */
const PODCAST_DRAG_TYPE = 'application/minabox-podcast-id';

interface PodcastListProps {
  podcasts: Podcast[];
  folders: MediaFolder[];
  currentFolderId: number | null;
  onNavigateFolder: (folderId: number | null) => void;
  onFolderCreate: (name: string, parentId: number | null) => Promise<void>;
  onFolderRename: (folder: MediaFolder, name: string) => Promise<void>;
  onFolderDelete: (folder: MediaFolder) => Promise<void>;
  onMovePodcastToFolder: (podcast: Podcast, folderId: number | null) => Promise<void>;
  onDelete: (podcast: Podcast) => void;
  onUpdate: (podcast: Podcast) => void;
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

export const PodcastList: React.FC<PodcastListProps> = ({
  podcasts,
  onDelete,
  onUpdate,
  onMovePodcastToFolder,
  ...viewProps
}) => {
  const { t } = useTranslation('media');
  const [podcastToEdit, setPodcastToEdit] = useState<Podcast | null>(null);

  const thumbnail = (podcast: Podcast, size: number) =>
    podcast.cover_art_url ? (
      <Box
        component="img"
        src={podcast.cover_art_url}
        alt=""
        sx={{ width: size, height: size, objectFit: 'cover', borderRadius: size > 28 ? 1 : 0.5, display: 'block' }}
      />
    ) : (
      <Box color="text.secondary" sx={{ display: 'flex' }}>
        <PodcastsIcon fontSize="small" />
      </Box>
    );

  const descriptor: CollectionDescriptor<Podcast> = {
    dragType: PODCAST_DRAG_TYPE,
    treeLabel: t('tabs.podcasts'),
    searchPlaceholder: t('podcasts.search_placeholder'),
    emptyText: t('podcasts.no_podcasts'),
    sortLabel: t('podcasts.sort.label'),
    sortOpenLabel: t('podcasts.sort.open'),
    sortAscLabel: t('podcasts.sort.asc'),
    sortDescLabel: t('podcasts.sort.desc'),
    resetLabel: t('podcasts.sort.reset'),
    defaultSortKey: 'title',
    sortOptions: [
      { key: 'title', label: t('podcasts.fields.title'), value: (p) => p.title.toLowerCase() },
      { key: 'last_played_at', label: t('podcasts.fields.last_played'), value: (p) => timeValue(p.last_played_at) },
      { key: 'last_fetched_at', label: t('podcasts.fields.last_fetched'), value: (p) => timeValue(p.last_fetched_at) },
    ],
    searchFields: (p) => [p.title, p.description],
    renderThumbnail: thumbnail,
    renderIcon: () => <PodcastsIcon fontSize="small" color="primary" />,
    renderCardBody: (p) =>
      p.latest_episode_title ? (
        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }} noWrap>
          {t('podcasts.latest_episode')}: {p.latest_episode_title}
        </Typography>
      ) : null,
    renderListSecondary: (p) => (
      <Box component="span" display="flex" flexDirection="column" gap={0.25}>
        {p.latest_episode_title && (
          <Typography component="span" variant="caption" display="block" noWrap>
            {t('podcasts.latest_episode')}: {p.latest_episode_title}
            {p.latest_episode_published_at &&
              ` (${new Date(p.latest_episode_published_at).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })})`}
          </Typography>
        )}
        <Box component="span" display="flex" gap={1} flexWrap="wrap" alignItems="center">
          <LastPlayedCaption
            value={p.last_played_at}
            label={t('podcasts.last_played')}
            emptyLabel={t('never_played')}
          />
          <LastPlayedCaption
            value={p.last_fetched_at}
            label={t('podcasts.last_fetched_label')}
            separator
          />
        </Box>
      </Box>
    ),
    columns: [
      { key: 'cover', label: '', width: 44, render: (p) => thumbnail(p, 28) },
      { key: 'title', label: t('podcasts.fields.title'), sortable: true, width: '32%', render: (p) => p.title },
      {
        key: 'latest_episode',
        label: t('podcasts.latest_episode'),
        width: '32%',
        render: (p) => p.latest_episode_title || '—',
      },
      {
        key: 'last_fetched_at',
        label: t('podcasts.fields.last_fetched'),
        sortable: true,
        render: (p) => <RelativeTimeCell value={p.last_fetched_at} />,
      },
      {
        key: 'last_played_at',
        label: t('podcasts.fields.last_played'),
        sortable: true,
        render: (p) => <RelativeTimeCell value={p.last_played_at} />,
      },
    ],
    actions: [
      {
        key: 'play',
        label: t('tracks.play'),
        icon: <PlayArrowIcon fontSize="small" />,
        primary: true,
        onClick: (p) => audioApi.play({ podcast_id: p.id }),
      },
      {
        key: 'edit',
        label: t('podcasts.edit'),
        icon: <EditIcon fontSize="small" />,
        onClick: (p) => setPodcastToEdit(p),
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
      <CollectionView<Podcast>
        {...viewProps}
        items={podcasts}
        onMoveToFolder={onMovePodcastToFolder}
        descriptor={descriptor}
      />

      <PodcastEditDialog
        open={!!podcastToEdit}
        podcast={podcastToEdit}
        onClose={() => setPodcastToEdit(null)}
        onSaved={(updated) => { onUpdate(updated); setPodcastToEdit(null); }}
        onChanged={(updated) => { onUpdate(updated); setPodcastToEdit(updated); }}
      />
    </>
  );
};
