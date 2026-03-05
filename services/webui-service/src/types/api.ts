/**
 * TypeScript type definitions for the Minabox Backend REST API.
 * Mirrors the Pydantic schemas from the backend-service.
 */

// ============================================================================
// Enums
// ============================================================================

export type ContentType = 'playlist' | 'track' | 'stream' | 'podcast';
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
  cover_art_url?: string | null;
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
  cover_art_url: string | null;
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
// Podcasts
// ============================================================================

export interface Podcast {
  id: number;
  title: string;
  rss_url: string;
  description: string | null;
  cover_art_url: string | null;
  last_fetched_at: string | null;
  last_played_at: string | null;
  created_at: string;
  latest_episode_title: string | null;
  latest_episode_published_at: string | null;
}

export interface PodcastEpisode {
  id: number;
  podcast_id: number;
  title: string;
  source_uri: string;
  published_at: string | null;
  duration_ms: number | null;
  created_at: string;
}

export interface PodcastCreate {
  title: string;
  rss_url: string;
  description?: string | null;
  cover_art_url?: string | null;
}

export interface PodcastUpdate {
  title?: string;
  rss_url?: string;
  description?: string | null;
  cover_art_url?: string | null;
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
  track_cover_art_url?: string | null;
}

export interface QueueItem {
  track_id: number;
  title: string;
  artist: string | null;
  album: string | null;
  index: number;
  is_current: boolean;
}

export type RepeatMode = 'none' | 'all';

export interface AudioSessionResponse {
  queue: QueueItem[];
  repeat_mode: RepeatMode;
  shuffle: boolean;
}

export interface VolumeRequest {
  volume: number;
}

export interface PlayRequest {
  playlist_id?: number;
  track_id?: number;
  stream_id?: number;
  podcast_id?: number;
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
  cpu_percent?: number | null;
  memory_mb?: number | null;
  memory_percent?: number | null;
}

export interface SystemStatus {
  services: ServiceStatus[];
  device_id: string;
  uptime_seconds?: number | null;
}

// ============================================================================
// Config: Audio
// ============================================================================

export interface AudioDeviceItem {
  id: string;
  name: string;
  card_name: string;
  alsa_device: string;
  priority: number;
}

export interface AudioDevicesResponse {
  devices: AudioDeviceItem[];
}

export interface AudioConfig {
  output_device_type: string;
  output_device_name: string;
  enabled_output_devices?: string[];
  device_display_names?: Record<string, string>;
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
// Config: Display (OLED)
// ============================================================================

export type DisplayElementType = 'volume' | 'sleep_timer' | 'mute' | 'play_state' | 'clock' | 'error_state' | 'repeat' | 'shuffle' | 'bluetooth';

/** Conditional element types – only render an item when the state is active.
 *  If too many of these share an area, some may be dropped at runtime. */
export const DISPLAY_CONDITIONAL_TYPES: ReadonlySet<DisplayElementType> = new Set([
  'sleep_timer', 'mute', 'error_state', 'repeat', 'shuffle', 'bluetooth',
]);

/** Maximum items the renderer can show per area. */
export const DISPLAY_AREA_LIMITS: Record<number, number> = { 0: 6, 1: 3, 2: 3 };

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

/** Font size: small (9px), medium (12px), large (14px) */
export type DisplayFontSize = 'small' | 'medium' | 'large';

/**
 * Font family for the OLED display.
 * - default : PIL built-in bitmap font, always available
 * - sans     : DejaVu Sans          (apt: fonts-dejavu-core, usually pre-installed)
 * - mono     : DejaVu Sans Mono     (apt: fonts-dejavu-core)
 * - roboto   : Roboto Regular       (apt: fonts-roboto)
 * - ubuntu   : Ubuntu Regular       (apt: fonts-ubuntu)
 * - noto     : Noto Sans Regular    (apt: fonts-noto)
 * - liberation: Liberation Sans     (apt: fonts-liberation, often pre-installed)
 * - terminus : Terminus TTF         (apt: fonts-terminus)
 * Falls back to 'default' if the chosen font is not installed on the device.
 */
export type DisplayFont =
  | 'default'
  | 'sans'
  | 'mono'
  | 'roboto'
  | 'ubuntu'
  | 'noto'
  | 'liberation'
  | 'terminus';

export interface DisplayConfig {
  enabled: boolean;
  i2c_bus: number;
  i2c_address: number;
  font_size?: DisplayFontSize;
  font?: DisplayFont;
  elements: DisplayElement[];
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

export interface AllowedUsageTimeSlot {
  weekday: number; // 0=Monday .. 6=Sunday
  start: string;   // "HH:MM"
  end: string;     // "HH:MM"
}

export interface GeneralConfig {
  minabox_device_id: string;
  log_level: string;
  mqtt_broker: string;
  mqtt_port: number;
  disable_gpio: boolean;
  sleep_timer_minutes: number;
  bedtime_fade_enabled: boolean;
  bedtime_fade_duration_minutes: number;
  bedtime_fade_interval_seconds: number;
  bedtime_fade_step_percent: number;
  allowed_usage_times: AllowedUsageTimeSlot[];
  usage_times_enabled?: boolean;
  daily_limit_enabled?: boolean;
  daily_limit_minutes?: number;
  stop_playback_on_tag_remove?: boolean;
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
  | 'usage_denied'
  | 'button_action'
  | 'button_raw_event'
  | 'sleep_timer_status'
  | 'repeat_mode'
  | 'shuffle_mode'
  | 'service_status'
  | 'system_status'
  | 'system_alert'
  | 'system_alert_cleared'
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

export interface UsageDeniedMessage extends WebSocketMessage {
  type: 'usage_denied';
  data: {
    tag_id: string;
    timestamp: string;
  };
}

export interface ServiceStatusMessage extends WebSocketMessage {
  type: 'service_status';
  data: ServiceStatus;
}

/** Emitted by backend when button-service publishes a raw hardware event.
 *  Used by the WebUI hardware test-mode to show immediate feedback. */
export interface ButtonRawEventMessage extends WebSocketMessage {
  type: 'button_raw_event';
  data: {
    button_id: string | null;
    name: string | null;
    event_type: string | null;
    timestamp: string | null;
  };
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

// ============================================================================
// Listening stats (Parent Dashboard)
// ============================================================================

export interface MinutesPerDayItem {
  date: string;
  minutes: number;
}

export interface TopTagItem {
  tag_id: number;
  name: string | null;
  scan_count: number;
}

export interface TopPlaylistItem {
  playlist_id: number;
  name: string | null;
  play_count: number;
}

export interface HeatmapItem {
  hour: number;
  weekday: number;
  minutes: number;
}

export interface ListeningSummaryResponse {
  minutes_per_day: MinutesPerDayItem[];
  top_tags: TopTagItem[];
  top_playlists: TopPlaylistItem[];
  heatmap: HeatmapItem[];
}

export interface UsageTodayResponse {
  minutes_today: number;
  daily_limit_enabled: boolean;
  daily_limit_minutes: number;
}

export interface OverviewResponse {
  minutes_today: number;
  minutes_total: number;
  daily_limit_enabled: boolean;
  daily_limit_minutes: number;
  tags_count: number;
  tracks_count: number;
  streams_count: number;
  podcasts_count: number;
  playlists_count: number;
}
