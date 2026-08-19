import React from 'react';
import BuildIcon from '@mui/icons-material/Build';
import CableIcon from '@mui/icons-material/Cable';
import LockIcon from '@mui/icons-material/Lock';
import PaletteIcon from '@mui/icons-material/Palette';
import TerminalIcon from '@mui/icons-material/Terminal';
import VolumeUpIcon from '@mui/icons-material/VolumeUp';
import WifiIcon from '@mui/icons-material/Wifi';

/**
 * Symbol je Einstellungs-Gruppe – Pille auf dem Desktop, Zeilensymbol im
 * Akkordeon am Telefon.
 *
 * Bewusst *nicht* in `@/config/settingsIndex`: Dieser Index ist frei von
 * React-Inhalten, damit die CommandPalette dieselbe Struktur durchsuchen kann,
 * ohne Komponenten zu laden. Die Schluessel entsprechen `SettingsGroupMeta.key`.
 */
export const SETTINGS_GROUP_ICONS: Record<string, React.ReactNode> = {
  sound: <VolumeUpIcon />,
  appearance: <PaletteIcon />,
  devices: <CableIcon />,
  network: <WifiIcon />,
  maintenance: <BuildIcon />,
  security: <LockIcon />,
  advanced: <TerminalIcon />,
};
