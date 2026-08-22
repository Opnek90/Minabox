import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { systemApi } from '@/api/system';
import { apiErrorCode } from '@/utils/apiError';

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
  const { t, i18n } = useTranslation('admin');
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
      const fallback = t('system.logs_unavailable').replace('<service>', serviceName);
      const code = apiErrorCode(err);
      setError(code && i18n.exists(`errors:${code}`) ? t(`errors:${code}` as never) : fallback);
    } finally {
      setLoading(false);
    }
  }, [serviceName, t, i18n]);

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

