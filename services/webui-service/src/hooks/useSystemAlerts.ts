import { useCallback, useEffect, useState } from 'react';
import { systemApi, type SystemAlert } from '@/api/system';
import { useWebSocketEvent } from '@/contexts/WebSocketContext';

// Muss zum Kennwort in backend_service/core/update_check.py passen.
export const ALERT_UPDATE_AVAILABLE = 'update_available';

const SEVERITY: Record<SystemAlert['level'], number> = { info: 0, warning: 1, error: 2 };

/**
 * Aktive System-Alerts, nach Kennung getrennt (siehe system_alerts.py). Ein
 * einzelner Alert-Zustand wuerde Update-Hinweis und Uebertemperatur-Warnung
 * gegenseitig verdraengen, obwohl beide gleichzeitig gelten koennen - der
 * eine als Kopfzeilen-Icon, der andere als volle Hinweisleiste.
 */
export const useSystemAlerts = (): SystemAlert[] => {
  const [alerts, setAlerts] = useState<Record<string, SystemAlert>>({});

  useEffect(() => {
    systemApi.getAllAlerts()
      .then((res) => {
        setAlerts(Object.fromEntries(res.alerts.map((a) => [a.code, a])));
      })
      .catch(() => {});
  }, []);

  const handleSet = useCallback((message: { data: unknown }) => {
    const d = message.data as { level?: string; code?: string; message?: string };
    if (!d.code) return;
    const alert: SystemAlert = {
      code: d.code,
      level: (d.level as SystemAlert['level']) ?? 'info',
      message: d.message ?? '',
    };
    setAlerts((prev) => ({ ...prev, [alert.code]: alert }));
  }, []);

  const handleClear = useCallback((message: { data: unknown }) => {
    const d = message.data as { code?: string };
    if (!d.code) return;
    setAlerts((prev) => {
      if (!(d.code! in prev)) return prev;
      const next = { ...prev };
      delete next[d.code!];
      return next;
    });
  }, []);

  useWebSocketEvent('system_alert', handleSet);
  useWebSocketEvent('system_alert_cleared', handleClear);

  return Object.values(alerts).sort((a, b) => SEVERITY[b.level] - SEVERITY[a.level]);
};
