import apiClient from './client';
import type { Stream, StreamCreate, StreamUpdate } from '@/types/api';

export const streamsApi = {
  getAll: async (): Promise<Stream[]> => {
    const response = await apiClient.get<Stream[]>('/streams');
    return response.data;
  },

  getById: async (id: number): Promise<Stream> => {
    const response = await apiClient.get<Stream>(`/streams/${id}`);
    return response.data;
  },

  create: async (data: StreamCreate): Promise<Stream> => {
    const response = await apiClient.post<Stream>('/streams', data);
    return response.data;
  },

  update: async (id: number, data: StreamUpdate): Promise<Stream> => {
    const response = await apiClient.put<Stream>(`/streams/${id}`, data);
    return response.data;
  },

  delete: async (id: number): Promise<void> => {
    await apiClient.delete(`/streams/${id}`);
  },

  uploadCover: async (streamId: number, file: File): Promise<Stream> => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await apiClient.post<Stream>(`/streams/${streamId}/cover`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  },

  deleteCover: async (streamId: number): Promise<Stream> => {
    const response = await apiClient.delete<Stream>(`/streams/${streamId}/cover`);
    return response.data;
  },
};
