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
  temperature_celsius?: number | null;
}

export interface SystemAlert {
  code: string;
  level: 'warning' | 'info' | 'error';
  message: string;
}

export interface CurrentAlertResponse {
  alert: SystemAlert | null;
}

export interface TemperatureHistoryResponse {
  readings: Array<{ t: string; celsius: number }>;
}

export type DebugExportMediaLevel = 'off' | 'counts' | 'filenames';

export interface DebugExportOptions {
  preset?: 'minimal' | 'recommended' | 'full';
  system?: boolean;
  logs?: boolean;
  settings?: boolean;
  network?: boolean;
  media?: DebugExportMediaLevel;
  history?: boolean;
  client?: boolean;
  include_db?: boolean;
}

export interface DebugExportPreviewFile {
  path: string;
  bytes: number;
  /** One plain-language sentence about what this file is. */
  description: string;
}

export interface DebugExportPreview {
  export_id: string;
  filename: string;
  total_bytes: number;
  schema_version: number;
  files: DebugExportPreviewFile[];
  collectors_failed: { name: string; error?: string }[];
  expires_in_seconds: number;
}

export interface DebugExportCapabilities {
  schema_version: number;
  /** True when the caller may pick the tiers that need an admin session. */
  elevated: boolean;
  presets: string[];
  blocks: { key: string; always_on: boolean; requires_session?: boolean; levels?: string[] }[];
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

  /** Current system alert (e.g. overheating) for the global bar. */
  getCurrentAlert: async (): Promise<CurrentAlertResponse> => {
    const response = await apiClient.get<CurrentAlertResponse>('/system/current-alert');
    return response.data;
  },

  /** Temperature readings for the last N hours (default 24). */
  getTemperatureHistory: async (hours = 24): Promise<TemperatureHistoryResponse> => {
    const response = await apiClient.get<TemperatureHistoryResponse>('/system/temperature-history', {
      params: { hours },
    });
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

  /**
   * Build the debug export. Runs without a login, but the backend forces the
   * standard tier unless an admin session is present.
   */
  createDebugExport: async (
    options: DebugExportOptions,
    client?: unknown
  ): Promise<Blob> => {
    const response = await apiClient.post<Blob>(
      '/system/debug-export',
      { options, client },
      { responseType: 'blob', timeout: 180000 }
    );
    return response.data;
  },

  /**
   * Build the archive and describe its contents without downloading it yet.
   * The backend keeps the built archive, so the download does not rebuild it.
   */
  previewDebugExport: async (
    options: DebugExportOptions,
    client?: unknown
  ): Promise<DebugExportPreview> => {
    const response = await apiClient.post<DebugExportPreview>(
      '/system/debug-export/preview',
      { options, client },
      { timeout: 180000 }
    );
    return response.data;
  },

  /** Fetch the archive the preview already built. */
  downloadDebugExport: async (exportId: string): Promise<Blob> => {
    const response = await apiClient.get<Blob>(
      `/system/debug-export/download/${encodeURIComponent(exportId)}`,
      { responseType: 'blob', timeout: 180000 }
    );
    return response.data;
  },

  /** Which parts of the export this caller is allowed to select. */
  getDebugExportCapabilities: async (): Promise<DebugExportCapabilities> => {
    const response = await apiClient.get<DebugExportCapabilities>('/system/debug-export/options');
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

  /**
   * Start the Minabox update in the background. Poll getUpdateStatus().
   * `targets` pins exactly those services to exactly those versions; every
   * other service is pinned to what it currently runs, so a targeted update
   * cannot drag anything else along. Omit it to move everything to latest.
   * The same call performs a rollback - just with older version numbers.
   */
  updateMinabox: async (
    targets?: Record<string, string>,
  ): Promise<{ ok: boolean; message?: string; steps?: string[] }> => {
    const response = await apiClient.post<{ ok: boolean; message?: string; steps?: string[] }>(
      '/system/update-minabox',
      { targets: targets ?? null, backup: true },
    );
    return response.data;
  },

  /** Progress and output of the running or last update. */
  getUpdateStatus: async (): Promise<UpdateStatusResponse> => {
    const response = await apiClient.get<UpdateStatusResponse>('/system/update-minabox/status');
    return response.data;
  },

  /**
   * Compare the running versions against the published ones.
   * `force` bypasses the cache - that is what the button does.
   */
  getUpdateCheck: async (force = false): Promise<UpdateCheckResponse> => {
    const response = await apiClient.get<UpdateCheckResponse>('/system/update-check', {
      params: force ? { force: true } : undefined,
      timeout: 30000,
    });
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

  /** List paired Bluetooth devices. Requires Host-Helper. */
  bluetoothPaired: async (): Promise<{
    devices: Array<{ address: string; name: string | null; connected?: boolean }>;
  }> => {
    const response = await apiClient.get<{
      devices: Array<{ address: string; name: string | null; connected?: boolean }>;
    }>('/system/bluetooth/paired');
    return response.data;
  },

  /** Connect to paired Bluetooth device. Requires Host-Helper. */
  bluetoothConnect: async (address: string): Promise<{ ok: boolean; address?: string }> => {
    const response = await apiClient.post<{ ok: boolean; address?: string }>(
      '/system/bluetooth/connect',
      { address },
    );
    return response.data;
  },

  /** Disconnect Bluetooth device. Requires Host-Helper. */
  bluetoothDisconnect: async (address: string): Promise<{ ok: boolean; address?: string }> => {
    const response = await apiClient.post<{ ok: boolean; address?: string }>(
      '/system/bluetooth/disconnect',
      { address },
    );
    return response.data;
  },

  /** Remove (unpair) Bluetooth device. Requires Host-Helper. */
  bluetoothRemove: async (address: string): Promise<{ ok: boolean; address?: string }> => {
    const response = await apiClient.post<{ ok: boolean; address?: string }>(
      '/system/bluetooth/remove',
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

/** Release notes of one version, per category and language. */
export interface ReleaseNotes {
  added?: { de: string[]; en: string[] };
  improved?: { de: string[]; en: string[] };
  fixed?: { de: string[]; en: string[] };
}

export interface ServiceRelease {
  version: string;
  date: string | null;
  notes: ReleaseNotes;
}

export interface ServiceUpdateInfo {
  service: string;
  /** Version currently running, from the container's image label. */
  installed: string;
  /** Newest published version, or null for an image we do not publish. */
  latest: string | null;
  update_available: boolean;
  /** False for images from other projects, e.g. the MQTT broker. */
  managed: boolean;
  /** Every skipped release between installed and latest, newest first. */
  releases: ServiceRelease[];
  /** The manifest knows this version but the registry does not have it yet. */
  pending_publish?: boolean;
}

export interface UpdateCheckResponse {
  checked_at: string;
  from_cache: boolean;
  update_available: boolean;
  /** Set when the check could not reach the manifest; never implies an update. */
  error: string | null;
  services: ServiceUpdateInfo[];
}

export interface UpdateStatusResponse {
  running: boolean;
  /** What the last run set, per service. */
  targets?: Record<string, string>;
  /** Versions to go back to, per service - empty when there is nothing to undo. */
  rollback?: Record<string, string>;
  step: number | null;
  step_count: number | null;
  /** repo | pull | restart | verify */
  step_key: string | null;
  steps: string[];
  exit_code: number | null;
  log: string;
  /** True while the Host-Helper itself is being restarted by the update. */
  unreachable?: boolean;
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
