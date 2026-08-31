import React, { useCallback, useEffect, useState } from 'react';
import { Box } from '@mui/material';
import { systemApi, type NetworkStatusResponse } from '@/api/system';
import { NetworkStatusBlock } from '@/components/admin/network/NetworkStatusBlock';
import { WifiBlock } from '@/components/admin/network/WifiBlock';
import { HostnameBlock } from '@/components/admin/network/HostnameBlock';
import { IPv4Block } from '@/components/admin/network/IPv4Block';

/**
 * Everything that makes the box reachable on the network.
 *
 * Four topics with no shared state - Wi-Fi, hotspot, fixed IP, device name -
 * used to sit here in one file with 23 `useState`. Each block now loads its own.
 *
 * What stays here is the one thing that really is shared: the status card on
 * top shows mode and address, and both the Wi-Fi and the IP configuration can
 * change both. The card used to stay on the old state after a hotspot start,
 * because it was only filled on the first load.
 */
export const NetworkPanel: React.FC = () => {
  const [status, setStatus] = useState<NetworkStatusResponse | null>(null);

  const refreshStatus = useCallback(async () => {
    try {
      setStatus(await systemApi.getNetworkStatus());
    } catch {
      setStatus(null);
    }
  }, []);

  useEffect(() => {
    void refreshStatus();
  }, [refreshStatus]);

  return (
    <Box>
      <NetworkStatusBlock status={status} />
      <WifiBlock onNetworkChanged={refreshStatus} />
      <HostnameBlock />
      <IPv4Block onNetworkChanged={refreshStatus} />
    </Box>
  );
};
