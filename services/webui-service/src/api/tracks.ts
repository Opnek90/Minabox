import apiClient from './client';
import type { Track, TrackCreate, TrackUpdate } from '@/types/api';

export interface MediaUrlInfo {
  valid: boolean;
  title: string;
  artist: string | null;
  duration_ms: number | null;
  thumbnail_url: string | null;
  video_id: string;
}

export const tracksApi = {
  getAll: async (): Promise<Track[]> => {
    const response = await apiClient.get<Track[]>('/tracks');
    return response.data;
  },

  getById: async (id: number): Promise<Track> => {
    const response = await apiClient.get<Track>(`/tracks/${id}`);
    return response.data;
  },

  create: async (data: TrackCreate): Promise<Track> => {
    const response = await apiClient.post<Track>('/tracks', data);
    return response.data;
  },

  upload: async (
    file: File,
    metadata: { title?: string; artist?: string; album?: string },
    onProgress?: (percent: number) => void
  ): Promise<Track> => {
    const formData = new FormData();
    formData.append('file', file);
    if (metadata.title) formData.append('title', metadata.title);
    if (metadata.artist) formData.append('artist', metadata.artist);
    if (metadata.album) formData.append('album', metadata.album);

    const response = await apiClient.post<Track>('/tracks/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (progressEvent) => {
        if (onProgress && progressEvent.total) {
          const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total);
          onProgress(percent);
        }
      },
    });
    return response.data;
  },

  /**
   * Fetch video metadata without downloading – used for the preview step
   * in MediaImportDialog.
   */
  validateUrl: async (url: string): Promise<MediaUrlInfo> => {
    const response = await apiClient.get<MediaUrlInfo>('/tracks/validate-url', {
      params: { url },
    });
    return response.data;
  },

  /**
   * Download a video from URL via the media-downloader-service and add it
   * as a track to the media library.
   */
  fromUrl: async (url: string): Promise<Track> => {
    const response = await apiClient.post<Track>('/tracks/from-url', null, {
      params: { url },
      // Downloads can take several minutes for long videos
      timeout: 300_000,
    });
    return response.data;
  },

  update: async (id: number, data: TrackUpdate): Promise<Track> => {
    const response = await apiClient.put<Track>(`/tracks/${id}`, data);
    return response.data;
  },

  delete: async (id: number): Promise<void> => {
    await apiClient.delete(`/tracks/${id}`);
  },

  uploadCover: async (trackId: number, file: File): Promise<Track> => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await apiClient.post<Track>(`/tracks/${trackId}/cover`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  },

  deleteCover: async (trackId: number): Promise<Track> => {
    const response = await apiClient.delete<Track>(`/tracks/${trackId}/cover`);
    return response.data;
  },
};
