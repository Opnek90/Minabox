import apiClient from './client';
import type {
  AudioDevicesResponse,
  AudioSessionResponse,
  AudioStatus,
  PlayRequest,
  RepeatMode,
  SleepTimerStatus,
  VolumeRequest,
} from '@/types/api';

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

  getSleepTimer: async (): Promise<SleepTimerStatus> => {
    const response = await apiClient.get<SleepTimerStatus>('/audio/sleep-timer');
    return response.data;
  },

  startSleepTimer: async (minutes: number): Promise<void> => {
    await apiClient.post('/audio/sleep-timer', { minutes });
  },

  cancelSleepTimer: async (): Promise<void> => {
    await apiClient.delete('/audio/sleep-timer');
  },

  getSession: async (): Promise<AudioSessionResponse> => {
    const response = await apiClient.get<AudioSessionResponse>('/audio/session');
    return response.data;
  },

  setRepeatMode: async (mode: RepeatMode): Promise<void> => {
    await apiClient.post('/audio/repeat', { mode });
  },

  setShuffle: async (shuffle: boolean): Promise<void> => {
    await apiClient.post('/audio/shuffle', { shuffle });
  },

  getDevices: async (enabledOnly = false): Promise<AudioDevicesResponse> => {
    const response = await apiClient.get<AudioDevicesResponse>('/audio/devices', {
      params: { enabled_only: enabledOnly },
    });
    return response.data;
  },

  switchDevice: async (alsaDevice: string): Promise<AudioStatus> => {
    const response = await apiClient.post<{ status: AudioStatus; timestamp: string }>(
      '/audio/switch-device',
      { alsa_device: alsaDevice }
    );
    return response.data.status;
  },

  switchDeviceNext: async (): Promise<AudioStatus> => {
    const response = await apiClient.post<{ status: AudioStatus; timestamp: string }>(
      '/audio/switch-device',
      { direction: 'next' }
    );
    return response.data.status;
  },
};
