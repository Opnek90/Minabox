import { useCallback, useEffect, useState } from 'react';
import { statsApi } from '@/api/stats';
import type { WeeklyReviewResponse } from '@/types/api';

export interface UseWeeklyReviewResult {
  /** 0 = current week, 1 = last week, ... */
  weekOffset: number;
  data: WeeklyReviewResponse | null;
  loading: boolean;
  error: string | null;
  /** Step one week into the past. */
  goPrev: () => void;
  /** Step one week towards the present; clamped at the current week. */
  goNext: () => void;
  reload: () => Promise<void>;
}

export function useWeeklyReview(initialOffset = 1): UseWeeklyReviewResult {
  const [weekOffset, setWeekOffset] = useState(initialOffset);
  const [data, setData] = useState<WeeklyReviewResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    setLoading(true);
    try {
      setData(await statsApi.getWeeklyReview(weekOffset));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load');
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [weekOffset]);

  useEffect(() => {
    void load();
  }, [load]);

  const goPrev = useCallback(() => setWeekOffset((o) => o + 1), []);
  const goNext = useCallback(() => setWeekOffset((o) => Math.max(0, o - 1)), []);

  return { weekOffset, data, loading, error, goPrev, goNext, reload: load };
}
