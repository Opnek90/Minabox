import React from 'react';
import { Box } from '@mui/material';
import { BackupBlock } from '@/components/admin/maintenance/BackupBlock';
import { UpdateBlock } from '@/components/admin/maintenance/UpdateBlock';
import { PowerBlock } from '@/components/admin/maintenance/PowerBlock';

/**
 * Sichern, aktualisieren, neu starten.
 *
 * Drei Bereiche, die sich keinen Zustand teilen und vorher trotzdem in einer
 * Datei mit 28 `useState` lagen. Die sichtbare Gliederung ist unveraendert:
 * dieselben drei Ueberschriften, dieselbe Knopfreihe.
 */
export const SystemMaintenanceSection: React.FC = () => (
  <Box>
    <BackupBlock />
    <UpdateBlock />
    <PowerBlock />
  </Box>
);
