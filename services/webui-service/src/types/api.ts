/**
 * TypeScript type definitions for the Minabox Backend REST API.
 * Mirrors the Pydantic schemas from the backend-service.
 */

// ============================================================================
// Enums
// ============================================================================

export type ContentType = 'playlist' | 'track' | 'stream';
export type SourceType = 'file' | 'remote';
export type AudioState = 'playing' | 'paused' | 'stopped' | 'error';
export type ServiceState = 'online' | 'offline' | 'error';
export type RFIDMode = 'normal' | 'learning';
export type LEDPatternType = 'solid' | 'blink' | 'pulse' | 'off';
export type ButtonMode = 'basic' | 'advanced';
export type ButtonType = 'push' | 'rotary';

// ============================================================================
// Tags
// ============================================================================

export interface Tag {
  id: number;
  tag_id: string;
  name: string | null;
  content_type: ContentType;
  content_id: number;
  created_at: string;
  updated_at: string;
  last_scanned_at: string | null;
}

export interface TagCreate {
  tag_id: string;
  name?: string | null;
  content_type: ContentType;
  content_id: number;
}

export interface TagUpdate {
  name?: string | null;
  content_type?: ContentType;
  content_id?: number;
}

export interface TagWithContent extends Tag {
  content_name?: string | null;
}

// ============================================================================
// Playlists
// ============================================================================

export interface Playlist {
  id: number;
  name: string;
  description: string | null;
  cover_art_url: string | null;
  created_at: string;
  updated_at: string;
  tracks?: PlaylistTrack[] | Track[];
}

/** Playlist as returned by GET /playlists/:id (includes tracks as Track[]) */
export interface PlaylistDetail extends Omit<Playlist, 'tracks'> {
  tracks: Track[];
}

export interface PlaylistCreate {
  name: string;
  description?: string | null;
}

export interface PlaylistUpdate {
  name?: string;
  description?: string | null;
  track_ids?: number[];
}

export interface PlaylistTrack {
  id: number;
  playlist_id: number;
  track_id: number;
  position: number;
  track: Track;
}

export interface PlaylistTrackAdd {
  track_id: number;
  position?: number;
}

// ============================================================================
// Tracks
// ============================================================================

export interface Track {
  id: number;
  title: string;
  artist: string | null;
  album: string | null;
  duration_ms: number | null;
  source_type: SourceType;
  source_uri: string;
  created_at: string;
  last_played_at: string | null;
}

export interface TrackCreate {
  title: string;
  artist?: string | null;
  album?: string | null;
  source_type: SourceType;
  source_uri: string;
}

export interface TrackUpdate {
  title?: string;
  artist?: string | null;
  album?: string | null;
}

// ============================================================================
// Streams
// ============================================================================

export interface Stream {
  id: number;
  title: string;
  artist: string | null;
  source_uri: string;
  created_at: string;
  last_played_at: string | null;
}

export interface StreamCreate {
  title: string;
  artist?: string | null;
  source_uri: string;
}

export interface StreamUpdate {
  title?: string;
  artist?: string | null;
  source_uri?: string;
}

// ============================================================================
// Audio
// ============================================================================

export interface AudioStatus {
  state: AudioState;
  track_id: number | null;
  source_type: SourceType | null;
  source_uri: string | null;
  position_ms: number;
  duration_ms: number | null;
  volume: number;
  timestamp: string;
  playlist_id?: number | null;
  playlist_position?: number | null;
  playlist_total?: number | null;
  track_title?: string | null;
  track_artist?: string | null;
  track_album?: string | null;
}

export interface VolumeRequest {
  volume: number;
}

export interface PlayRequest {
  playlist_id?: number;
  track_id?: number;
  stream_id?: number;
  position_ms?: number;
}

// ============================================================================
// System
// ============================================================================

export interface ServiceStatus {
  service: string;
  state: ServiceState;
  timestamp: string;
  version?: string | null;
}

export interface SystemStatus {
  services: ServiceStatus[];
  device_id: string;
  uptime_seconds?: number | null;
}

// ============================================================================
// Config: Audio
// ============================================================================

export interface AudioConfig {
  output_device_type: string;
  output_device_name: string;
  max_volume: number;
  default_volume: number;
  resume_on_startup?: boolean;
  fade_in_ms?: number;
  fade_out_ms?: number;
}

// ============================================================================
// Config: LED
// ============================================================================

export interface LEDPattern {
  pattern_type: LEDPatternType;
  duration_ms?: number | null;
  interval_ms?: number | null;
  repeat?: number | null;
}

export interface LED {
  id: string;
  name: string;
  gpio: number;
  bindings: Record<string, LEDPattern>;
}

export interface LEDConfig {
  leds: LED[];
}

// ============================================================================
// Config: Button
// ============================================================================

export interface ButtonConfig {
  buttons: Button[];
}

// ============================================================================
// Config: Display (OLED)
// ============================================================================

export type DisplayElementType = 'volume' | 'sleep_timer' | 'mute' | 'play_state' | 'clock' | 'error_state';

/** Area on the OLED: 0 = header (full width), 1 = left column, 2 = right column */
export type DisplayArea = 0 | 1 | 2;

export interface DisplayElement {
  id: string;
  type: DisplayElementType;
  enabled: boolean;
  order: number;
  /** Area: 0 = header, 1 = left, 2 = right */
  area?: DisplayArea;
}

/** Font size: small (8px), medium (10px), large (12px) */
export type DisplayFontSize = 'small' | 'medium' | 'large';
/** Font: default (built-in), sans, mono */
export type DisplayFont = 'default' | 'sans' | 'mono';

export interface DisplayConfig {
  enabled: boolean;
  i2c_bus: number;
  i2c_address: number;
  font_size?: DisplayFontSize;
  font?: DisplayFont;
  elements: DisplayElement[];
}

export interface Button {
  id: string;
  name: string;
  mode: ButtonMode;
  type: ButtonType;
  gpio?: number | null;
  clk?: number | null;
  dt?: number | null;
  sw?: number | null;
  action?: string | null;
  actions?: Record<string, string> | null;
}

// ============================================================================
// Config: RFID
// ============================================================================

export interface RFIDConfig {
  reader_type: string;
  interface: string;
  scan_interval_ms: number;
  duplicate_suppression_ms: number;
}

// ============================================================================
// Config: General (central .env-style settings)
// ============================================================================

export interface GeneralConfig {
  minabox_device_id: string;
  log_level: string;
  mqtt_broker: string;
  mqtt_port: number;
  disable_gpio: boolean;
  sleep_timer_minutes: number;
}

export interface SleepTimerStatus {
  active: boolean;
  remaining_ms: number | null;
}

export interface ServiceLogsResponse {
  service: string;
  lines: string;
  tail: number;
}

// ============================================================================
// WebSocket Messages
// ============================================================================

export type WebSocketMessageType =
  | 'audio_status'
  | 'rfid_scanned'
  | 'rfid_scanned_learning'
  | 'rfid_removed'
  | 'tag_not_found'
  | 'button_action'
  | 'sleep_timer_status'
  | 'service_status'
  | 'system_status'
  | 'error';

export interface WebSocketMessage {
  type: WebSocketMessageType;
  data: unknown;
  timestamp: string;
}

export interface AudioStatusMessage extends WebSocketMessage {
  type: 'audio_status';
  data: AudioStatus;
}

export interface RFIDScannedMessage extends WebSocketMessage {
  type: 'rfid_scanned' | 'rfid_scanned_learning';
  data: {
    tag_id: string;
  };
}

export interface ServiceStatusMessage extends WebSocketMessage {
  type: 'service_status';
  data: ServiceStatus;
}

// ============================================================================
// API Responses
// ============================================================================

export interface ErrorResponse {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

// ============================================================================
// RFID Learning Mode
// ============================================================================

export interface LearningModeRequest {
  enabled: boolean;
}

export interface LearningModeResponse {
  active: boolean;
  timestamp: string;
}

export interface ServiceStatus {
  service: string;
  state: ServiceState;
  timestamp: string;
  version?: string | null;
  // Optional – populated when Docker socket is available
  cpu_percent?: number | null;
  memory_mb?: number | null;
  memory_percent?: number | null;
}