import React, { useState } from 'react';
import {
  SpeedDial,
  SpeedDialAction,
  SpeedDialIcon,
} from '@mui/material';
import CloudUploadIcon from '@mui/icons-material/CloudUpload';
import CreateNewFolderIcon from '@mui/icons-material/CreateNewFolder';
import DownloadIcon from '@mui/icons-material/Download';
import LinkIcon from '@mui/icons-material/Link';
import PlaylistAddIcon from '@mui/icons-material/PlaylistAdd';
import PodcastsIcon from '@mui/icons-material/Podcasts';
import StreamIcon from '@mui/icons-material/Stream';
import { useTranslation } from 'react-i18next';

interface MediaFabProps {
  /** 0=Playlists, 1=Tracks, 2=Streams, 3=Podcasts */
  activeTab: number;
  onCreatePlaylist: () => void;
  onCreateFolder: () => void;
  onUpload: () => void;
  onRemoteTrack: () => void;
  onImport: () => void;
  onCreateStream: () => void;
  onCreatePodcast: () => void;
}

export const MediaFab: React.FC<MediaFabProps> = ({
  activeTab,
  onCreatePlaylist,
  onCreateFolder,
  onUpload,
  onRemoteTrack,
  onImport,
  onCreateStream,
  onCreatePodcast,
}) => {
  const { t } = useTranslation('media');
  const [open, setOpen] = useState(false);

  const actionsByTab: Record<number, { icon: React.ReactNode; name: string; onClick: () => void }[]> = {
    0: [
      { icon: <PlaylistAddIcon />, name: t('playlists.add_playlist'), onClick: onCreatePlaylist },
    ],
    1: [
      { icon: <CreateNewFolderIcon />, name: t('folders.new', { defaultValue: 'New Folder' }), onClick: onCreateFolder },
      { icon: <LinkIcon />, name: t('tracks.add_remote', { defaultValue: 'Remote Track' }), onClick: onRemoteTrack },
      { icon: <DownloadIcon />, name: t('tracks.import_from_url', { defaultValue: 'Import from URL' }), onClick: onImport },
      { icon: <CloudUploadIcon />, name: t('tracks.upload'), onClick: onUpload },
    ],
    2: [
      { icon: <StreamIcon />, name: t('tracks.add_stream'), onClick: onCreateStream },
    ],
    3: [
      { icon: <PodcastsIcon />, name: t('podcasts.add'), onClick: onCreatePodcast },
    ],
  };

  const actions = actionsByTab[activeTab] ?? [];

  return (
    <SpeedDial
      ariaLabel="Media actions"
      sx={{ position: 'fixed', bottom: 24, right: 24, zIndex: 1200 }}
      icon={<SpeedDialIcon />}
      open={open}
      onOpen={() => setOpen(true)}
      onClose={() => setOpen(false)}
    >
      {actions.map((action) => (
        <SpeedDialAction
          key={action.name}
          icon={action.icon}
          tooltipTitle={action.name}
          tooltipOpen
          onClick={() => {
            setOpen(false);
            action.onClick();
          }}
        />
      ))}
    </SpeedDial>
  );
};
