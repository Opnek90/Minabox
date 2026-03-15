import apiClient from './client';

export interface ScanEvent {
  id: number;
  tag_id: string;
  tag_name: string | null;
  media_title: string | null;
  media_type: string | null;
  scanned_at: string;
  action: 'play' | 'blocked' | 'unassigned';
}

export const scanHistoryApi = {
  getAll: async (params?: { limit?: number; offset?: number; tag_id?: string }): Promise<ScanEvent[]> => {
    const response = await apiClient.get<ScanEvent[]>('/scan-history/', { params });
    return response.data;
  },

  clear: async (): Promise<void> => {
    await apiClient.delete('/scan-history/');
  },
};
