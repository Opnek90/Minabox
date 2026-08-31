import React from 'react';
import { Box } from '@mui/material';
import { BackupBlock } from '@/components/admin/maintenance/BackupBlock';
import { UpdateBlock } from '@/components/admin/maintenance/UpdateBlock';
import { PowerBlock } from '@/components/admin/maintenance/PowerBlock';

/**
 * Back up, update, restart.
 *
 * Three areas that share no state and yet used to sit in one file with 28
 * `useState`. The visible structure is unchanged: the same three headings, the
 * same button row.
 */
export const SystemMaintenanceSection: React.FC = () => (
  <Box>
    <BackupBlock />
    <UpdateBlock />
    <PowerBlock />
  </Box>
);
