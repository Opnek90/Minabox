import React from 'react';
import { Box } from '@mui/material';
import { BackupBlock } from '@/components/admin/maintenance/BackupBlock';
import { AnalyticsRetentionBlock } from '@/components/admin/maintenance/AnalyticsRetentionBlock';
import { UpdateBlock } from '@/components/admin/maintenance/UpdateBlock';
import { PowerBlock } from '@/components/admin/maintenance/PowerBlock';

/**
 * Back up, update, restart.
 *
 * Areas that share no state and yet used to sit in one file with 28
 * `useState`. Which addons the box has moved out of here entirely: adding one
 * is not maintenance, and it now has its own group in the settings
 * (`components/admin/addons`).
 *
 * Retention sits right after the backup it shares a topic with - both are
 * about the box's own data, not a rule for the child, which is why it moved
 * off the parent dashboard (`docs/services/webui/Settings-Structure.md`).
 */
export const SystemMaintenanceSection: React.FC = () => (
  <Box>
    <BackupBlock />
    <AnalyticsRetentionBlock />
    <UpdateBlock />
    <PowerBlock />
  </Box>
);
