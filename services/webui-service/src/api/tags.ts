import apiClient from './client';
import type { Tag, TagCreate, TagUpdate, LearningModeResponse } from '@/types/api';

export const tagsApi = {
  getAll: async (): Promise<Tag[]> => {
    const response = await apiClient.get<Tag[]>('/tags');
    return response.data;
  },

  getById: async (id: number): Promise<Tag> => {
    const response = await apiClient.get<Tag>(`/tags/${id}`);
    return response.data;
  },

  create: async (data: TagCreate): Promise<Tag> => {
    const response = await apiClient.post<Tag>('/tags', data);
    return response.data;
  },

  /** Update tag by RFID tag_id (string UID, e.g. "82432B07"). */
  update: async (tagId: string, data: TagUpdate): Promise<Tag> => {
    const response = await apiClient.put<Tag>(`/tags/${tagId}`, data);
    return response.data;
  },

  /** Delete tag by RFID tag_id (string UID). */
  delete: async (tagId: string): Promise<void> => {
    await apiClient.delete(`/tags/${tagId}`);
  },

  setLearningMode: async (active: boolean): Promise<LearningModeResponse> => {
    const body = { enabled: active };
    const response = await apiClient.post<LearningModeResponse>('/rfid/learning-mode', body);
    return response.data;
  },
};
