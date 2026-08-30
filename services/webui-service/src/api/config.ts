import apiClient, { TIMEOUT } from './client';
import type {
  AudioConfig,
  LEDConfig,
  LEDPatternType,
  ButtonConfig,
  RFIDConfig,
  GeneralConfig,
  DisplayConfig,
} from '@/types/api';

export const configApi = {
  // Audio config
  getAudio: async (): Promise<AudioConfig> => {
    const response = await apiClient.get<AudioConfig>('/config/audio');
    return response.data;
  },

  updateAudio: async (data: Partial<AudioConfig>): Promise<AudioConfig> => {
    const response = await apiClient.put<AudioConfig>('/config/audio', data);
    return response.data;
  },

  // LED config
  getLeds: async (): Promise<LEDConfig> => {
    const response = await apiClient.get<LEDConfig>('/config/leds');
    return response.data;
  },

  updateLeds: async (data: LEDConfig): Promise<LEDConfig> => {
    const response = await apiClient.put<LEDConfig>('/config/leds', data);
    return response.data;
  },

  testLed: async (ledId: string): Promise<void> => {
    await apiClient.post('/config/leds/test', { led_id: ledId });
  },

  /** Shows a brief test pattern on the OLED. Rejects with 404 if none is attached. */
  testDisplay: async (): Promise<void> => {
    await apiClient.post('/config/display/test');
  },

  getLedStates: async (): Promise<string[]> => {
    const response = await apiClient.get<string[]>('/config/leds/states');
    return response.data;
  },

  getLedPatterns: async (): Promise<LEDPatternType[]> => {
    const response = await apiClient.get<LEDPatternType[]>('/config/leds/patterns');
    return response.data;
  },

  getButtonActions: async (): Promise<string[]> => {
    const response = await apiClient.get<string[]>('/config/buttons/actions');
    return response.data;
  },

  // Display config
  getDisplay: async (): Promise<DisplayConfig> => {
    const response = await apiClient.get<DisplayConfig>('/config/display');
    return response.data;
  },

  updateDisplay: async (data: DisplayConfig): Promise<DisplayConfig> => {
    const response = await apiClient.put<DisplayConfig>('/config/display', data);
    return response.data;
  },

  // Button config
  getButtons: async (): Promise<ButtonConfig> => {
    const response = await apiClient.get<ButtonConfig>('/config/buttons');
    return response.data;
  },

  updateButtons: async (data: ButtonConfig): Promise<ButtonConfig> => {
    const response = await apiClient.put<ButtonConfig>('/config/buttons', data);
    return response.data;
  },

  // RFID config
  getRfid: async (): Promise<RFIDConfig> => {
    const response = await apiClient.get<RFIDConfig>('/config/rfid');
    return response.data;
  },

  updateRfid: async (data: Partial<RFIDConfig>): Promise<RFIDConfig> => {
    const response = await apiClient.put<RFIDConfig>('/config/rfid', data);
    return response.data;
  },

  // General (central) config
  getGeneral: async (): Promise<GeneralConfig> => {
    const response = await apiClient.get<GeneralConfig>('/config/general');
    return response.data;
  },

  updateGeneral: async (data: Partial<GeneralConfig>): Promise<GeneralConfig> => {
    const response = await apiClient.put<GeneralConfig>('/config/general', data);
    return response.data;
  },

  // Logo
  uploadLogo: async (file: File): Promise<{ url: string }> => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await apiClient.post<{ url: string }>('/config/logo', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: TIMEOUT.UPLOAD,
    });
    return response.data;
  },

  deleteLogo: async (): Promise<void> => {
    await apiClient.delete('/config/logo');
  },
};
