import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { systemApi } from '@/api/system';

const AUTO_REFRESH_INTERVAL_MS = 5_000;

export interface UseServiceLogsResult {
  logsLines: string[];
  displayLines: string[];
  loading: boolean;
  error: string | null;
  autoRefresh: boolean;
  setAutoRefresh: (value: boolean) => void;
  refresh: () => Promise<void>;
}

export function useServiceLogs(serviceName: string, open: boolean): UseServiceLogsResult {
  const { t } = useTranslation('admin');
  const [logsLines, setLogsLines] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(false);

  const fetchLogs = useCallback(async () => {
    if (!serviceName) return;
    setLoading(true);
    setError(null);
    try {
      const res = await systemApi.getLogs(serviceName, 200);
      const lines = (res.lines ?? '').split('\n').filter(Boolean);
      setLogsLines(lines);
    } catch (err: unknown) {
      const res =
        err && typeof err === 'object' && 'response' in err
          ? (err as { response?: { status?: number; data?: { detail?: string } } }).response
          : undefined;
      const status = res?.status;
      const detail = res?.data?.detail;
      // #region agent log
      fetch('http://localhost:7587/ingest/956f1dfb-30a2-4644-a364-2be2e1ac338d', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Debug-Session-Id': '771350',
        },
        body: JSON.stringify({
          sessionId: '771350',
          location: 'ServiceLogsModal.tsx:fetchLogs',
          message: 'getLogs error',
          data: {
            status,
            detail: typeof detail === 'string' ? detail : undefined,
            serviceName,
          },
          timestamp: Date.now(),
          hypothesisId: 'H4,H5',
        }),
      }).catch(() => {});
      // #endregion
      const fallback = t('system.logs_unavailable').replace('<service>', serviceName);
      setError(detail && typeof detail === 'string' ? detail : fallback);
    } finally {
      setLoading(false);
    }
  }, [serviceName, t]);

  useEffect(() => {
    if (open && serviceName) {
      void fetchLogs();
    }
  }, [open, serviceName, fetchLogs]);

  useEffect(() => {
    if (!open || !autoRefresh || !serviceName) return;
    const interval = setInterval(() => {
      void fetchLogs();
    }, AUTO_REFRESH_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [open, autoRefresh, serviceName, fetchLogs]);

  const displayLines = useMemo(
    () => [...logsLines].reverse(),
    [logsLines],
  );

  return {
    logsLines,
    displayLines,
    loading,
    error,
    autoRefresh,
    setAutoRefresh,
    refresh: fetchLogs,
  };
}

