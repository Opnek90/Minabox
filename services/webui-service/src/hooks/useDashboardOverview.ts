import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useToast } from '@/contexts/ToastContext';
import { statsApi } from '@/api/stats';
import type { OverviewResponse } from '@/types/api';

export interface UseDashboardOverviewResult {
  data: OverviewResponse | null;
  loading: boolean;
  refreshing: boolean;
  resetDialogOpen: boolean;
  resetting: boolean;
  openResetDialog: () => void;
  closeResetDialog: () => void;
  load: () => Promise<void>;
  confirmReset: () => Promise<void>;
}

export function useDashboardOverview(): UseDashboardOverviewResult {
  const { t } = useTranslation('common');
  const { showSuccess, showError } = useToast();

  const [data, setData] = useState<OverviewResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [resetDialogOpen, setResetDialogOpen] = useState(false);
  const [resetting, setResetting] = useState(false);

  // Track whether initial data has been loaded to distinguish loading vs. refreshing.
  // Using a ref instead of `data` as a dependency avoids recreating `load` on every
  // fetch completion, which previously caused an infinite refreshing=true loop (#94).
  const hasDataRef = useRef(false);

  const load = useCallback(async () => {
    if (!hasDataRef.current) setLoading(true);
    else setRefreshing(true);
    try {
      const res = await statsApi.getOverview();
      hasDataRef.current = true;
      setData(res);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []); // stable – no data dependency

  useEffect(() => {
    void load();
    const interval = setInterval(() => {
      void load();
    }, 60_000);
    return () => clearInterval(interval);
  }, [load]);

  const openResetDialog = useCallback(() => {
    setResetDialogOpen(true);
  }, []);

  const closeResetDialog = useCallback(() => {
    if (!resetting) {
      setResetDialogOpen(false);
    }
  }, [resetting]);

  const confirmReset = useCallback(async () => {
    setResetting(true);
    try {
      await statsApi.resetListeningStats();
      setResetDialogOpen(false);
      await load();
      showSuccess(
        t('dashboard.reset_success'),
      );
    } catch {
      showError(
        t('dashboard.reset_error'),
      );
    } finally {
      setResetting(false);
    }
  }, [load, showSuccess, showError, t]);

  return {
    data,
    loading,
    refreshing,
    resetDialogOpen,
    resetting,
    openResetDialog,
    closeResetDialog,
    load,
    confirmReset,
  };
}
