import apiClient from './client';
import type { Playlist, PlaylistCreate, PlaylistUpdate, PlaylistDetail, PlaylistTrackAdd } from '@/types/api';

export const playlistsApi = {
  getAll: async (): Promise<Playlist[]> => {
    const response = await apiClient.get<Playlist[]>('/playlists');
    return response.data;
  },

  getById: async (id: number): Promise<PlaylistDetail> => {
    const response = await apiClient.get<PlaylistDetail>(`/playlists/${id}`);
    return response.data;
  },

  create: async (data: PlaylistCreate): Promise<Playlist> => {
    const response = await apiClient.post<Playlist>('/playlists', data);
    return response.data;
  },

  update: async (id: number, data: PlaylistUpdate): Promise<Playlist> => {
    const response = await apiClient.put<Playlist>(`/playlists/${id}`, data);
    return response.data;
  },

  delete: async (id: number): Promise<void> => {
    await apiClient.delete(`/playlists/${id}`);
  },

  addTrack: async (playlistId: number, data: PlaylistTrackAdd): Promise<Playlist> => {
    const response = await apiClient.post<Playlist>(`/playlists/${playlistId}/tracks`, data);
    return response.data;
  },

  removeTrack: async (playlistId: number, trackId: number): Promise<Playlist> => {
    const response = await apiClient.delete<Playlist>(
      `/playlists/${playlistId}/tracks/${trackId}`
    );
    return response.data;
  },

  reorderTracks: async (
    playlistId: number,
    trackIds: number[]
  ): Promise<Playlist> => {
    const response = await apiClient.put<Playlist>(`/playlists/${playlistId}/tracks/reorder`, {
      track_ids: trackIds,
    });
    return response.data;
  },

  uploadCover: async (playlistId: number, file: File): Promise<Playlist> => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await apiClient.post<Playlist>(`/playlists/${playlistId}/cover`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  },

  deleteCover: async (playlistId: number): Promise<Playlist> => {
    const response = await apiClient.delete<Playlist>(`/playlists/${playlistId}/cover`);
    return response.data;
  },
};
