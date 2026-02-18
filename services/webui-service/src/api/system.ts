import apiClient from './client';
import type { SystemStatus, ServiceLogsResponse } from '@/types/api';

export const systemApi = {
  getStatus: async (): Promise<SystemStatus> => {
    const response = await apiClient.get<SystemStatus>('/system/status');
    return response.data;
  },

  getLogs: async (service: string, tail = 200): Promise<ServiceLogsResponse> => {
    const response = await apiClient.get<ServiceLogsResponse>('/system/logs', {
      params: { service, tail },
    });
    return response.data;
  },

  restart: async (): Promise<void> => {
    await apiClient.post('/system/restart');
  },
};
