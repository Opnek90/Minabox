import React from 'react';
import BuildIcon from '@mui/icons-material/Build';
import ExtensionIcon from '@mui/icons-material/Extension';
import CableIcon from '@mui/icons-material/Cable';
import LibraryMusicIcon from '@mui/icons-material/LibraryMusic';
import LockIcon from '@mui/icons-material/Lock';
import PaletteIcon from '@mui/icons-material/Palette';
import PlayCircleOutlineIcon from '@mui/icons-material/PlayCircleOutline';
import TerminalIcon from '@mui/icons-material/Terminal';
import VolumeUpIcon from '@mui/icons-material/VolumeUp';
import WifiIcon from '@mui/icons-material/Wifi';

/**
 * An icon per settings group - a pill on the desktop, a row icon in the
 * accordion on the phone.
 *
 * Deliberately *not* in `@/config/settingsIndex`: that index is free of React
 * content, so the CommandPalette can search the same structure without loading
 * components. The keys match `SettingsGroupMeta.key`.
 */
export const SETTINGS_GROUP_ICONS: Record<string, React.ReactNode> = {
  playback: <PlayCircleOutlineIcon />,
  sound: <VolumeUpIcon />,
  appearance: <PaletteIcon />,
  media: <LibraryMusicIcon />,
  devices: <CableIcon />,
  addons: <ExtensionIcon />,
  network: <WifiIcon />,
  maintenance: <BuildIcon />,
  security: <LockIcon />,
  advanced: <TerminalIcon />,
};
