import React from 'react';
import { Box } from '@mui/material';
import { BackupBlock } from '@/components/admin/maintenance/BackupBlock';
import { ComponentsBlock } from '@/components/admin/maintenance/ComponentsBlock';
import { UpdateBlock } from '@/components/admin/maintenance/UpdateBlock';
import { PowerBlock } from '@/components/admin/maintenance/PowerBlock';

/**
 * Back up, update, change the components, restart.
 *
 * Areas that share no state and yet used to sit in one file with 28
 * `useState`. The components sit directly under the version block: both are
 * "what is on this box", and both get there through the same kind of run.
 */
export const SystemMaintenanceSection: React.FC = () => (
  <Box>
    <BackupBlock />
    <UpdateBlock />
    <ComponentsBlock />
    <PowerBlock />
  </Box>
);
