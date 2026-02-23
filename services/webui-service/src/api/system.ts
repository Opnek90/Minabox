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
  uptime_seconds: number | null;
  memory: {
    total_mb: number;
    available_mb: number;
    percent_used: number;
  } | null;
  cpu: { load_1m: number; load_5m?: number; load_15m?: number; percent_used: number | null } | null;
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

  /** Shutdown the host (Pi). Requires Host-Helper. */
  shutdownHost: async (): Promise<void> => {
    await apiClient.post('/system/shutdown');
  },

  /** Get host kernel or docker unit logs (syslog). Requires Host-Helper. */
  getSyslog: async (n = 200, source: 'kernel' | 'docker' = 'kernel'): Promise<SyslogResponse> => {
    const response = await apiClient.get<SyslogResponse>('/system/syslog', {
      params: { n, source },
    });
    return response.data;
  },

  /** Download backup ZIP (DB, configs, state). Requires Host-Helper. */
  downloadBackup: async (): Promise<Blob> => {
    const response = await apiClient.get<Blob>('/system/backup/download', {
      responseType: 'blob',
    });
    return response.data;
  },

  /** Restore from backup ZIP. Requires Host-Helper. Containers will restart. */
  restoreBackup: async (file: File): Promise<{ ok: boolean; message?: string }> => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await apiClient.post<{ ok: boolean; message?: string }>(
      '/system/backup/restore',
      formData,
      {
        headers: { 'Content-Type': 'multipart/form-data' },
      }
    );
    return response.data;
  },

  /** Set host timezone (e.g. Europe/Berlin). Requires Host-Helper. */
  setTimezone: async (timezone: string): Promise<{ ok: boolean; timezone?: string }> => {
    const response = await apiClient.put<{ ok: boolean; timezone?: string }>(
      '/system/timezone',
      { timezone },
    );
    return response.data;
  },

  /** Get host time status (timezone, NTP sync, local time). Requires Host-Helper. */
  getTimeStatus: async (): Promise<TimeStatusResponse> => {
    const response = await apiClient.get<TimeStatusResponse>('/system/time-status');
    return response.data;
  },

  /** Get host hostname. Requires Host-Helper. */
  getHostname: async (): Promise<{ hostname: string | null }> => {
    const response = await apiClient.get<{ hostname: string | null }>('/system/hostname');
    return response.data;
  },

  /** Set host hostname. Requires Host-Helper. */
  setHostname: async (hostname: string): Promise<{ ok: boolean; hostname: string }> => {
    const response = await apiClient.put<{ ok: boolean; hostname: string }>(
      '/system/hostname',
      { hostname },
    );
    return response.data;
  },

  /** Get board LED state (stealth). Requires Host-Helper. */
  getBoardLeds: async (): Promise<BoardLedsResponse> => {
    const response = await apiClient.get<BoardLedsResponse>('/system/board-leds');
    return response.data;
  },

  /** Set board LEDs (stealth on/off). Requires Host-Helper. */
  setBoardLeds: async (stealth: boolean): Promise<{ ok: boolean; stealth: boolean }> => {
    const response = await apiClient.put<{ ok: boolean; stealth: boolean }>(
      '/system/board-leds',
      { stealth },
    );
    return response.data;
  },

  /** Get current IP config (DHCP/manual). Requires Host-Helper. */
  getNetwork: async (): Promise<NetworkResponse> => {
    const response = await apiClient.get<NetworkResponse>('/system/network');
    return response.data;
  },

  /** Set IP config (DHCP or manual). Requires Host-Helper. */
  setNetwork: async (config: NetworkConfig): Promise<{ ok: boolean; method: string }> => {
    const response = await apiClient.put<{ ok: boolean; method: string }>(
      '/system/network',
      config,
    );
    return response.data;
  },

  /** Change system user password. Requires Host-Helper. Never logged. */
  setPassword: async (username: string, newPassword: string): Promise<{ ok: boolean; message?: string }> => {
    const response = await apiClient.post<{ ok: boolean; message?: string }>(
      '/system/password',
      { username, new_password: newPassword },
    );
    return response.data;
  },

  /** Run docker system prune. Requires Host-Helper. */
  dockerPrune: async (): Promise<{ ok: boolean; message?: string; summary?: string }> => {
    const response = await apiClient.post<{ ok: boolean; message?: string; summary?: string }>(
      '/system/docker-prune',
    );
    return response.data;
  },

  /** Get SSH enabled/active on host. Requires Host-Helper. */
  getSshStatus: async (): Promise<{ enabled: boolean; active: boolean }> => {
    const response = await apiClient.get<{ enabled: boolean; active: boolean }>('/system/ssh-status');
    return response.data;
  },

  /** Enable or disable SSH on host. Requires Host-Helper. */
  setSshToggle: async (enable: boolean): Promise<{ ok: boolean; enabled: boolean; active: boolean }> => {
    const response = await apiClient.post<{ ok: boolean; enabled: boolean; active: boolean }>(
      '/system/ssh-toggle',
      { enable },
    );
    return response.data;
  },

  /** Factory reset: clear DB/config, optional audio, start hotspot. Requires Host-Helper. */
  factoryReset: async (deleteAudio: boolean): Promise<{ ok: boolean; message?: string }> => {
    const response = await apiClient.post<{ ok: boolean; message?: string }>(
      '/system/factory-reset',
      { delete_audio: deleteAudio },
    );
    return response.data;
  },

  /** Run Minabox update (docker compose pull + up -d). Requires Host-Helper. */
  updateMinabox: async (): Promise<{ ok: boolean; message?: string }> => {
    const response = await apiClient.post<{ ok: boolean; message?: string }>('/system/update-minabox');
    return response.data;
  },

  /** Get current version and whether update is available. Requires Host-Helper. */
  getVersion: async (): Promise<VersionResponse> => {
    const response = await apiClient.get<VersionResponse>('/system/version');
    return response.data;
  },

  /** Run OS update (apt upgrade) on host. Requires Host-Helper. Starts in background. */
  updateOs: async (): Promise<{ ok: boolean; message?: string }> => {
    const response = await apiClient.post<{ ok: boolean; message?: string }>('/system/update-os');
    return response.data;
  },

  /** Get OS update log and running status. Requires Host-Helper. */
  getUpdateOsLog: async (): Promise<{ running: boolean; log: string }> => {
    const response = await apiClient.get<{ running: boolean; log: string }>('/system/update-os/log');
    return response.data;
  },

  /** Scan for WiFi networks. Requires Host-Helper. */
  wifiScan: async (): Promise<WifiScanResponse> => {
    const response = await apiClient.get<WifiScanResponse>('/system/wifi/scan');
    return response.data;
  },

  /** Connect to WiFi. Requires Host-Helper. */
  wifiConnect: async (ssid: string, password: string): Promise<{ ok: boolean; ssid?: string }> => {
    const response = await apiClient.post<{ ok: boolean; ssid?: string }>(
      '/system/wifi/connect',
      { ssid, password },
    );
    return response.data;
  },

  /** Start WiFi hotspot. Requires Host-Helper. */
  wifiHotspotStart: async (ssid?: string, password?: string): Promise<WifiHotspotResponse> => {
    const response = await apiClient.post<WifiHotspotResponse>(
      '/system/wifi/hotspot/start',
      { ssid: ssid ?? 'Minabox-Setup', password: password ?? '' },
    );
    return response.data;
  },

  /** Stop WiFi hotspot. Requires Host-Helper. */
  wifiHotspotStop: async (): Promise<{ ok: boolean }> => {
    const response = await apiClient.post<{ ok: boolean }>('/system/wifi/hotspot/stop');
    return response.data;
  },

  /** Get hotspot status. Requires Host-Helper. */
  wifiHotspotStatus: async (): Promise<WifiHotspotStatusResponse> => {
    const response = await apiClient.get<WifiHotspotStatusResponse>('/system/wifi/hotspot/status');
    return response.data;
  },

  /** List USB devices. Requires Host-Helper. */
  usbDevices: async (): Promise<UsbDevicesResponse> => {
    const response = await apiClient.get<UsbDevicesResponse>('/system/usb/devices');
    return response.data;
  },

  /** List files on USB device. Requires Host-Helper. */
  usbFiles: async (deviceId: string): Promise<UsbFilesResponse> => {
    const response = await apiClient.get<UsbFilesResponse>(`/system/usb/${encodeURIComponent(deviceId)}/files`);
    return response.data;
  },

  /** Import paths from USB to audio storage. Requires Host-Helper. */
  usbImport: async (deviceId: string, sourcePaths: string[]): Promise<{ ok: boolean; files_copied?: number }> => {
    const response = await apiClient.post<{ ok: boolean; files_copied?: number }>(
      '/system/usb/import',
      { device_id: deviceId, source_paths: sourcePaths },
    );
    return response.data;
  },

  /** Eject USB device. Requires Host-Helper. */
  usbEject: async (deviceId: string): Promise<{ ok: boolean }> => {
    const response = await apiClient.post<{ ok: boolean }>('/system/usb/eject', { device_id: deviceId });
    return response.data;
  },

  /** Scan for Bluetooth devices. Requires Host-Helper. */
  bluetoothScan: async (): Promise<{ devices: Array<{ address: string; name: string | null }> }> => {
    const response = await apiClient.get<{ devices: Array<{ address: string; name: string | null }> }>('/system/bluetooth/scan');
    return response.data;
  },

  /** Pair with Bluetooth device. Requires Host-Helper. */
  bluetoothPair: async (address: string): Promise<{ ok: boolean; address?: string }> => {
    const response = await apiClient.post<{ ok: boolean; address?: string }>(
      '/system/bluetooth/pair',
      { address },
    );
    return response.data;
  },
};

export interface UsbDevice {
  id: string;
  device: string;
  size: string;
  fstype: string;
  mountpoint: string | null;
  label: string | null;
}

export interface UsbDevicesResponse {
  devices: UsbDevice[];
}

export interface UsbFilesResponse {
  path: string;
  entries: Array<{ path: string; name: string; type: string }>;
}

export interface WifiScanResponse {
  networks: Array<{ ssid: string; signal: number }>;
}

export interface WifiHotspotResponse {
  ok: boolean;
  ssid: string;
  password?: string;
  message?: string;
}

export interface WifiHotspotStatusResponse {
  active: boolean;
  ssid: string | null;
}

export interface TimeStatusResponse {
  timezone: string | null;
  ntp_sync: boolean;
  local_time: string | null;
}

export interface VersionResponse {
  current_version: string;
  current_commit: string | null;
  update_available: boolean;
}

export interface BoardLedsResponse {
  stealth: boolean;
  power_led: 'on' | 'off';
  activity_led: 'on' | 'off';
}

export interface NetworkResponse {
  method: 'dhcp' | 'manual';
  address: string | null;
  netmask: string | null;
  gateway: string | null;
  dns: string | null;
}

export interface NetworkConfig {
  method: 'dhcp' | 'manual';
  address?: string | null;
  netmask?: string | null;
  gateway?: string | null;
  dns?: string | null;
}

export interface SyslogResponse {
  lines: string[];
  source: string;
}
