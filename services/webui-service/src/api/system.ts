import apiClient from './client';
import type { SystemStatus, ServiceLogsResponse } from '@/types/api';

export interface AudioPathResponse {
  path: string;
}

export interface MoveStatusResponse {
  status: 'idle' | 'running' | 'done' | 'error';
  total: number;
  current: number;
  error: string | null;
}

export interface HostStatusResponse {
  hostname: string | null;
  ip: string | null;
  memory: {
    total_mb: number;
    available_mb: number;
    percent_used: number;
  } | null;
  cpu: { load_1m: number; percent_used: number | null } | null;
  disk: {
    path: string;
    total_gb: number;
    used_gb: number;
    percent_used: number;
  } | null;
}

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

  getAudioPath: async (): Promise<AudioPathResponse> => {
    const response = await apiClient.get<AudioPathResponse>('/system/audio-path');
    return response.data;
  },

  putAudioPath: async (path: string): Promise<{ ok: boolean; audio_files_path?: string }> => {
    const response = await apiClient.put<{ ok: boolean; audio_files_path?: string }>(
      '/system/audio-path',
      { path },
    );
    return response.data;
  },

  /** Start moving media from source to destination (async). Returns 202 when started; poll getMoveStatus() for progress. */
  moveAudio: async (source: string, destination: string): Promise<{ ok: boolean; status?: string }> => {
    const response = await apiClient.post<{ ok: boolean; status?: string }>(
      '/system/move-audio',
      { source, destination },
    );
    return response.data;
  },

  getMoveStatus: async (): Promise<MoveStatusResponse> => {
    const response = await apiClient.get<MoveStatusResponse>('/system/move-status');
    return response.data;
  },

  getHostStatus: async (): Promise<HostStatusResponse> => {
    const response = await apiClient.get<HostStatusResponse>('/system/host-status');
    return response.data;
  },

  /** Reboot the host (Pi). Requires Host-Helper. */
  rebootHost: async (): Promise<void> => {
    await apiClient.post('/system/reboot');
  },
};
