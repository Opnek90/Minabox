import React, { useCallback, useEffect, useState } from 'react';
import { Box } from '@mui/material';
import { systemApi, type NetworkStatusResponse } from '@/api/system';
import { NetworkStatusBlock } from '@/components/admin/network/NetworkStatusBlock';
import { WifiBlock } from '@/components/admin/network/WifiBlock';
import { HostnameBlock } from '@/components/admin/network/HostnameBlock';
import { IPv4Block } from '@/components/admin/network/IPv4Block';

/**
 * Alles, was die Box im Netzwerk erreichbar macht.
 *
 * Vier Themen ohne gemeinsamen Zustand - WLAN, Hotspot, feste IP, Geraetename -
 * lagen hier in einer Datei mit 23 `useState`. Jeder Block laedt jetzt seins.
 *
 * Was hier bleibt, ist das eine, was wirklich geteilt ist: die Status-Karte
 * oben zeigt Modus und Adresse, und WLAN wie IP-Konfiguration koennen beides
 * aendern. Frueher blieb die Karte nach einem Hotspot-Start auf dem alten
 * Stand stehen, weil sie nur beim ersten Laden gefuellt wurde.
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
