import apiClient from './client';
import type {
  Podcast,
  PodcastCreate,
  PodcastEpisode,
  PodcastUpdate,
} from '@/types/api';

export const podcastsApi = {
  list: async (): Promise<Podcast[]> => {
    const response = await apiClient.get<Podcast[]>('/podcasts');
    return response.data;
  },

  get: async (id: number): Promise<Podcast> => {
    const response = await apiClient.get<Podcast>(`/podcasts/${id}`);
    return response.data;
  },

  create: async (data: PodcastCreate): Promise<Podcast> => {
    const response = await apiClient.post<Podcast>('/podcasts', data);
    return response.data;
  },

  update: async (id: number, data: PodcastUpdate): Promise<Podcast> => {
    const response = await apiClient.put<Podcast>(`/podcasts/${id}`, data);
    return response.data;
  },

  delete: async (id: number): Promise<void> => {
    await apiClient.delete(`/podcasts/${id}`);
  },

  listEpisodes: async (podcastId: number): Promise<PodcastEpisode[]> => {
    const response = await apiClient.get<PodcastEpisode[]>(
      `/podcasts/${podcastId}/episodes`
    );
    return response.data;
  },

  uploadCover: async (podcastId: number, file: File): Promise<Podcast> => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await apiClient.post<Podcast>(`/podcasts/${podcastId}/cover`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  },

  deleteCover: async (podcastId: number): Promise<Podcast> => {
    const response = await apiClient.delete<Podcast>(`/podcasts/${podcastId}/cover`);
    return response.data;
  },
};
