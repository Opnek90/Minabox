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
      { icon: <PlaylistAddIcon fontSize="small" />, name: t('playlists.add_playlist'), onClick: onCreatePlaylist },
    ],
    1: [
      { icon: <CreateNewFolderIcon fontSize="small" />, name: t('folders.new', { defaultValue: 'New Folder' }), onClick: onCreateFolder },
      { icon: <LinkIcon fontSize="small" />, name: t('tracks.add_remote', { defaultValue: 'Remote Track' }), onClick: onRemoteTrack },
      { icon: <DownloadIcon fontSize="small" />, name: t('tracks.import_from_url', { defaultValue: 'Import from URL' }), onClick: onImport },
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
      {/* Backdrop closes the menu on outside click */}
      <Backdrop open={open} onClick={() => setOpen(false)} sx={{ zIndex: 1199 }} invisible />

      {/* Action list – renders above the FAB */}
      <Box
        sx={{
          position: 'fixed',
          bottom: 88,   // FAB height (56) + gap (8) + bottom offset (24)
          right: 24,
          zIndex: 1200,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'flex-end',
          gap: 1,
          pointerEvents: open ? 'auto' : 'none',
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

      {/* Main FAB */}
      <Fab
        color="primary"
        aria-label="Media actions"
        onClick={() => setOpen((prev) => !prev)}
        sx={{
          position: 'fixed',
          bottom: 24,
          right: 24,
          zIndex: 1200,
          transition: 'transform 0.2s',
          transform: open ? 'rotate(45deg)' : 'rotate(0deg)',
        }}
      >
        {open ? <CloseIcon /> : <AddIcon />}
      </Fab>
    </>
  );
};
