import apiClient from './client';
import type { Track, TrackCreate, TrackUpdate, TrackFolder, TrackFolderCreate, TrackFolderUpdate } from '@/types/api';

export interface MediaUrlInfo {
  valid: boolean;
  title: string;
  artist: string | null;
  duration_ms: number | null;
  thumbnail_url: string | null;
  video_id: string;
}

export interface DownloadStatusResponse {
  track_id: number;
  /** "pending" | "downloading" | "done" | "error" | "unknown" */
  status: string;
  error: string | null;
  /** "fetching_info" | "downloading" | "converting" | "finalizing" | "saving", while status is "downloading" */
  stage?: string | null;
  /** 0-100, only meaningful while stage is "downloading" */
  percent?: number | null;
}

export const trackFoldersApi = {
  getAll: async (): Promise<TrackFolder[]> => {
    const response = await apiClient.get<TrackFolder[]>('/tracks/folders');
    return response.data;
  },

  getById: async (id: number): Promise<TrackFolder> => {
    const response = await apiClient.get<TrackFolder>(`/tracks/folders/${id}`);
    return response.data;
  },

  create: async (data: TrackFolderCreate): Promise<TrackFolder> => {
    const response = await apiClient.post<TrackFolder>('/tracks/folders', data);
    return response.data;
  },

  update: async (id: number, data: TrackFolderUpdate): Promise<TrackFolder> => {
    const response = await apiClient.put<TrackFolder>(`/tracks/folders/${id}`, data);
    return response.data;
  },

  delete: async (id: number): Promise<void> => {
    await apiClient.delete(`/tracks/folders/${id}`);
  },
};

export const tracksApi = {
  getAll: async (folderId?: number | 'root'): Promise<Track[]> => {
    const params: Record<string, string | number> = {};
    if (folderId === 'root') params.folder_id = 0;
    else if (folderId !== undefined) params.folder_id = folderId;
    const response = await apiClient.get<Track[]>('/tracks', { params });
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
    metadata: { title?: string; artist?: string; album?: string; folderId?: number | null },
    onProgress?: (percent: number) => void
  ): Promise<Track> => {
    const formData = new FormData();
    formData.append('file', file);
    if (metadata.title) formData.append('title', metadata.title);
    if (metadata.artist) formData.append('artist', metadata.artist);
    if (metadata.album) formData.append('album', metadata.album);
    if (metadata.folderId != null) formData.append('folder_id', String(metadata.folderId));

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

  validateUrl: async (url: string): Promise<MediaUrlInfo> => {
    const response = await apiClient.get<MediaUrlInfo>('/tracks/validate-url', {
      params: { url },
    });
    return response.data;
  },

  /**
   * Start an async background download for a URL.
   * Returns { track_id, status: "pending" | "done" } immediately (HTTP 202 or 200 for duplicates).
   */
  fromUrl: async (
    url: string,
    overrides?: { title?: string; artist?: string; album?: string },
  ): Promise<{ track_id: number; status: string }> => {
    const response = await apiClient.post<{ track_id: number; status: string }>(
      '/tracks/from-url',
      null,
      { params: { url, ...overrides }, timeout: 15_000 },
    );
    return response.data;
  },

  /**
   * Poll the download status of a track imported via fromUrl().
   * Status values: "pending" | "downloading" | "done" | "error" | "unknown"
   */
  getDownloadStatus: async (trackId: number): Promise<DownloadStatusResponse> => {
    const response = await apiClient.get<DownloadStatusResponse>(
      `/tracks/${trackId}/download-status`,
    );
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
