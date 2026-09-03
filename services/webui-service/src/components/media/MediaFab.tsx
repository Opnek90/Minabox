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
import MicIcon from '@mui/icons-material/Mic';
import PodcastsIcon from '@mui/icons-material/Podcasts';
import StreamIcon from '@mui/icons-material/Stream';
import { useTranslation } from 'react-i18next';
import { useAudioStatus } from '@/hooks/useAudioStatus';
import { useFeatureInstalled } from '@/contexts/CapabilitiesContext';
import { useLayout } from '@/hooks/useLayout';
import { MINI_PLAYER_HEIGHT } from '@/components/common/MiniPlayer';
import { MOBILE_BOTTOM_NAV_HEIGHT, SAFE_AREA_BOTTOM } from '@/components/common/Navigation';

/** The MediaPage tabs. The overview has no create actions of its own. */
export type MediaTab = 'overview' | 'playlists' | 'tracks' | 'streams' | 'podcasts';

interface MediaFabProps {
  tab: MediaTab;
  onCreatePlaylist: () => void;
  onCreateFolder: () => void;
  onUpload: () => void;
  onRecord: () => void;
  onRemoteTrack: () => void;
  onImport: () => void;
  onCreateStream: () => void;
  onCreateStreamFolder: () => void;
  onCreatePodcast: () => void;
  onCreatePodcastFolder: () => void;
}

// FAB size (MUI default) + gap above it
const FAB_SIZE = 56;
const FAB_GAP = 8;
// Base bottom offset when MiniPlayer is not visible
const FAB_BOTTOM_DEFAULT = 24;

export const MediaFab: React.FC<MediaFabProps> = ({
  tab,
  onCreatePlaylist,
  onCreateFolder,
  onUpload,
  onRecord,
  onRemoteTrack,
  onImport,
  onCreateStream,
  onCreateStreamFolder,
  onCreatePodcast,
  onCreatePodcastFolder,
}) => {
  const { t } = useTranslation('media');
  const [open, setOpen] = useState(false);
  // Only at phone widths is there a BottomNav under the FAB; from tablet up
  // the navigation sits on the side as a rail.
  const { isMobile } = useLayout();

  const audioStatus = useAudioStatus();
  const isMiniPlayerVisible =
    audioStatus !== null && audioStatus.state !== 'stopped';

  // "Import from URL" downloads via the media downloader. Without that
  // component the action drops out; "remote track" (stream URL) stays.
  const mediaDownloaderInstalled = useFeatureInstalled('media_downloader');

  // Shift the FAB above the MiniPlayer bar (if visible) and the mobile
  // BottomNavigation (always present on mobile, MediaPage has no /player route)
  const fabBottomPx =
    FAB_BOTTOM_DEFAULT +
    (isMiniPlayerVisible ? MINI_PLAYER_HEIGHT : 0) +
    (isMobile ? MOBILE_BOTTOM_NAV_HEIGHT : 0);

  // On mobile, additionally lift it by the device safe area (gesture bar).
  const safeOffset = isMobile ? ` + ${SAFE_AREA_BOTTOM}` : '';
  const fabBottom = `calc(${fabBottomPx}px${safeOffset})`;

  // The action menu sits directly above the FAB
  const menuBottom = `calc(${fabBottomPx + FAB_SIZE + FAB_GAP}px${safeOffset})`;

  const actionsByTab: Partial<Record<MediaTab, { icon: React.ReactNode; name: string; onClick: () => void }[]>> = {
    playlists: [
      { icon: <PlaylistAddIcon fontSize="small" />, name: t('playlists.add_playlist'), onClick: onCreatePlaylist },
    ],
    tracks: [
      { icon: <CreateNewFolderIcon fontSize="small" />, name: t('folders.new'), onClick: onCreateFolder },
      { icon: <LinkIcon fontSize="small" />, name: t('tracks.add_remote'), onClick: onRemoteTrack },
      ...(mediaDownloaderInstalled
        ? [{ icon: <DownloadIcon fontSize="small" />, name: t('tracks.import_from_url'), onClick: onImport }]
        : []),
      { icon: <CloudUploadIcon fontSize="small" />, name: t('tracks.upload'), onClick: onUpload },
      { icon: <MicIcon fontSize="small" />, name: t('tracks.record'), onClick: onRecord },
    ],
    streams: [
      { icon: <CreateNewFolderIcon fontSize="small" />, name: t('folders.new'), onClick: onCreateStreamFolder },
      { icon: <StreamIcon fontSize="small" />, name: t('tracks.add_stream'), onClick: onCreateStream },
    ],
    podcasts: [
      { icon: <CreateNewFolderIcon fontSize="small" />, name: t('folders.new'), onClick: onCreatePodcastFolder },
      { icon: <PodcastsIcon fontSize="small" />, name: t('podcasts.add'), onClick: onCreatePodcast },
    ],
  };

  const actions = actionsByTab[tab] ?? [];

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
                // Put the hover tint as an overlay on the opaque paper, do not
                // replace the background colour -- otherwise the action becomes
                // translucent and the list behind it flashes through (#134).
                '&:hover': {
                  bgcolor: 'background.paper',
                  backgroundImage: (theme) =>
                    `linear-gradient(${theme.palette.action.hover}, ${theme.palette.action.hover})`,
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
