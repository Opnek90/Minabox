import React, { useState } from 'react';
import {
  Backdrop,
  Box,
  Fab,
  Paper,
  Typography,
  Zoom,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import CloseIcon from '@mui/icons-material/Close';
import CloudUploadIcon from '@mui/icons-material/CloudUpload';
import CreateNewFolderIcon from '@mui/icons-material/CreateNewFolder';
import DownloadIcon from '@mui/icons-material/Download';
import LinkIcon from '@mui/icons-material/Link';
import PlaylistAddIcon from '@mui/icons-material/PlaylistAdd';
import PodcastsIcon from '@mui/icons-material/Podcasts';
import StreamIcon from '@mui/icons-material/Stream';
import { useTranslation } from 'react-i18next';
import { useAudioStatus } from '@/hooks/useAudioStatus';
import { MINI_PLAYER_HEIGHT } from '@/components/common/MiniPlayer';

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

// FAB size (MUI default) + gap above it
const FAB_SIZE = 56;
const FAB_GAP = 8;
// Base bottom offset when MiniPlayer is not visible
const FAB_BOTTOM_DEFAULT = 24;

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

  const audioStatus = useAudioStatus();
  const isMiniPlayerVisible =
    audioStatus !== null && audioStatus.state !== 'stopped';

  // Shift the FAB above the MiniPlayer bar when it is visible
  const fabBottom = isMiniPlayerVisible
    ? FAB_BOTTOM_DEFAULT + MINI_PLAYER_HEIGHT
    : FAB_BOTTOM_DEFAULT;

  // The action menu sits directly above the FAB
  const menuBottom = fabBottom + FAB_SIZE + FAB_GAP;

  const actionsByTab: Record<number, { icon: React.ReactNode; name: string; onClick: () => void }[]> = {
    0: [
      { icon: <PlaylistAddIcon fontSize="small" />, name: t('playlists.add_playlist'), onClick: onCreatePlaylist },
    ],
    1: [
      { icon: <CreateNewFolderIcon fontSize="small" />, name: t('folders.new'), onClick: onCreateFolder },
      { icon: <LinkIcon fontSize="small" />, name: t('tracks.add_remote'), onClick: onRemoteTrack },
      { icon: <DownloadIcon fontSize="small" />, name: t('tracks.import_from_url'), onClick: onImport },
      { icon: <CloudUploadIcon fontSize="small" />, name: t('tracks.upload'), onClick: onUpload },
    ],
    2: [
      { icon: <StreamIcon fontSize="small" />, name: t('tracks.add_stream'), onClick: onCreateStream },
    ],
    3: [
      { icon: <PodcastsIcon fontSize="small" />, name: t('podcasts.add'), onClick: onCreatePodcast },
    ],
  };

  const actions = actionsByTab[activeTab] ?? [];

  const handleAction = (fn: () => void) => {
    setOpen(false);
    fn();
  };

  return (
    <>
      <Backdrop open={open} onClick={() => setOpen(false)} sx={{ zIndex: 1199 }} invisible />

      <Box
        sx={{
          position: 'fixed',
          bottom: menuBottom,
          right: 24,
          zIndex: 1200,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'flex-end',
          gap: 1,
          pointerEvents: open ? 'auto' : 'none',
          transition: 'bottom 0.3s ease',
        }}
      >
        {actions.map((action, i) => (
          <Zoom
            key={action.name}
            in={open}
            style={{ transitionDelay: open ? `${i * 40}ms` : `${(actions.length - 1 - i) * 30}ms` }}
          >
            <Paper
              component="button"
              elevation={4}
              onClick={() => handleAction(action.onClick)}
              sx={{
                display: 'flex',
                alignItems: 'center',
                gap: 1.5,
                px: 2,
                py: 1,
                minWidth: 180,
                border: 'none',
                cursor: 'pointer',
                borderRadius: '24px',
                bgcolor: 'background.paper',
                color: 'text.primary',
                whiteSpace: 'nowrap',
                '&:hover': {
                  bgcolor: 'action.hover',
                },
              }}
            >
              <Box
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  width: 28,
                  height: 28,
                  borderRadius: '50%',
                  bgcolor: 'primary.main',
                  color: 'primary.contrastText',
                  flexShrink: 0,
                }}
              >
                {action.icon}
              </Box>
              <Typography variant="body2" fontWeight={500}>
                {action.name}
              </Typography>
            </Paper>
          </Zoom>
        ))}
      </Box>

      <Fab
        color="primary"
        aria-label={t('fab.aria_label')}
        onClick={() => setOpen((prev) => !prev)}
        sx={{
          position: 'fixed',
          bottom: fabBottom,
          right: 24,
          zIndex: 1200,
          transition: 'bottom 0.3s ease, transform 0.2s',
          transform: open ? 'rotate(45deg)' : 'rotate(0deg)',
        }}
      >
        {open ? <CloseIcon /> : <AddIcon />}
      </Fab>
    </>
  );
};
