import apiClient from './client';
import type {
  Stream,
  StreamCreate,
  StreamFolder,
  StreamFolderCreate,
  StreamFolderUpdate,
  StreamUpdate,
} from '@/types/api';

export const streamFoldersApi = {
  getAll: async (): Promise<StreamFolder[]> => {
    const response = await apiClient.get<StreamFolder[]>('/streams/folders');
    return response.data;
  },

  getById: async (id: number): Promise<StreamFolder> => {
    const response = await apiClient.get<StreamFolder>(`/streams/folders/${id}`);
    return response.data;
  },

  create: async (data: StreamFolderCreate): Promise<StreamFolder> => {
    const response = await apiClient.post<StreamFolder>('/streams/folders', data);
    return response.data;
  },

  update: async (id: number, data: StreamFolderUpdate): Promise<StreamFolder> => {
    const response = await apiClient.put<StreamFolder>(`/streams/folders/${id}`, data);
    return response.data;
  },

  delete: async (id: number): Promise<void> => {
    await apiClient.delete(`/streams/folders/${id}`);
  },
};

export const streamsApi = {
  getAll: async (folderId?: number | 'root'): Promise<Stream[]> => {
    const params: Record<string, string | number> = {};
    if (folderId === 'root') params.folder_id = 0;
    else if (folderId !== undefined) params.folder_id = folderId;
    const response = await apiClient.get<Stream[]>('/streams', { params });
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
