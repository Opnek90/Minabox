import { useCallback, useEffect, useMemo, useState } from 'react';
import { statsApi } from '@/api/stats';
import type {
  HeatmapItem,
  ListeningSummaryResponse,
  MinutesPerDayItem,
} from '@/types/api';

export interface UseStatsDashboardResult {
  fromDate: string;
  toDate: string;
  setFromDate: (value: string) => void;
  setToDate: (value: string) => void;
  loading: boolean;
  error: string | null;
  data: ListeningSummaryResponse | null;
  maxMinutes: number;
  heatmapMax: number;
  load: () => Promise<void>;
}

function getDefaultDates(): { from: string; to: string } {
  const end = new Date();
  const start = new Date();
  start.setDate(start.getDate() - 13);
  return {
    from: start.toISOString().slice(0, 10),
    to: end.toISOString().slice(0, 10),
  };
}

export function useStatsDashboard(): UseStatsDashboardResult {
  const defaults = getDefaultDates();
  const [fromDate, setFromDate] = useState(defaults.from);
  const [toDate, setToDate] = useState(defaults.to);
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<ListeningSummaryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    setLoading(true);
    try {
      const res = await statsApi.getListeningSummary(fromDate, toDate);
      setData(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load');
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [fromDate, toDate]);

  useEffect(() => {
    void load();
  }, [load]);

  const maxMinutes = useMemo(
    () =>
      data?.minutes_per_day?.length
        ? Math.max(...data.minutes_per_day.map((d: MinutesPerDayItem) => d.minutes), 1)
        : 1,
    [data],
  );

  const heatmapMax = useMemo(
    () =>
      data?.heatmap?.length
        ? Math.max(...data.heatmap.map((h: HeatmapItem) => h.minutes), 1)
        : 1,
    [data],
  );

  return {
    fromDate,
    toDate,
    setFromDate,
    setToDate,
    loading,
    error,
    data,
    maxMinutes,
    heatmapMax,
    load,
  };
}

