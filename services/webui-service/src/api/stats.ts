import apiClient from './client';
import type { ListeningSummaryResponse, UsageTodayResponse } from '@/types/api';

export const statsApi = {
  getListeningSummary: async (
    fromDate: string,
    toDate: string
  ): Promise<ListeningSummaryResponse> => {
    const response = await apiClient.get<ListeningSummaryResponse>(
      '/stats/listening-summary',
      { params: { from_date: fromDate, to_date: toDate } }
    );
    return response.data;
  },

  getUsageToday: async (): Promise<UsageTodayResponse> => {
    const response = await apiClient.get<UsageTodayResponse>('/stats/usage-today');
    return response.data;
  },
};
