import apiClient from './client';
import type { AudioStatus, PlayRequest, VolumeRequest } from '@/types/api';

export const audioApi = {
  getStatus: async (): Promise<AudioStatus> => {
    const response = await apiClient.get<AudioStatus>('/audio/status');
    return response.data;
  },

  play: async (request?: PlayRequest): Promise<void> => {
    await apiClient.post('/audio/play', request ?? {});
  },

  pause: async (): Promise<void> => {
    await apiClient.post('/audio/pause');
  },

  stop: async (): Promise<void> => {
    await apiClient.post('/audio/stop');
  },

  next: async (): Promise<void> => {
    await apiClient.post('/audio/next');
  },

  previous: async (): Promise<void> => {
    await apiClient.post('/audio/prev');
  },

  setVolume: async (volume: number): Promise<void> => {
    const body: VolumeRequest = { volume };
    await apiClient.post('/audio/volume', body);
  },
};
