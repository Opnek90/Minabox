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
/**
 * 'degraded' is a service that answers but says it cannot do its job -
 * no usable GPIO pin, no broker, a configured sound card that is gone.
 * Its container is running and Docker calls it healthy, so without this it
 * was shown green.
 */
export type ServiceState = 'online' | 'degraded' | 'offline' | 'error';

/** A service that is up, whether or not it is fully working. */
export const isServiceUp = (state: ServiceState): boolean =>
  state === 'online' || state === 'degraded';
export type RFIDMode = 'normal' | 'learning';
/** All supported LED pattern types. 'glow' requires PWMLED (Software PWM). */
export type LEDPatternType = 'solid' | 'blink' | 'pulse' | 'off' | 'glow';
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
  /** When true, tag is blocked: no playback, fires tag_blocked MQTT event instead */
  disabled?: boolean;
}

export interface TagCreate {
  tag_id: string;
  name?: string | null;
  content_type: ContentType;
  content_id: number;
  disabled?: boolean;
}

export interface TagUpdate {
  name?: string | null;
  /**
   * An omitted field is left unchanged; an explicit `null` clears it.
   *
   * The backend tells the two apart by looking at the raw request body, and
   * unassigning a tag needs `content_type` AND `content_id` set to null -
   * clearing only one leaves a tag that still claims to point at a track
   * while pointing at nothing.
   */
  content_type?: ContentType | null;
  content_id?: number | null;
  disabled?: boolean;
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
// Track Folders
// ============================================================================

export interface TrackFolder {
  id: number;
  name: string;
  parent_id: number | null;
  created_at: string;
  updated_at: string | null;
}

export interface TrackFolderCreate {
  name: string;
  parent_id?: number | null;
}

export interface TrackFolderUpdate {
  name?: string;
  parent_id?: number | null;
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
  folder_id?: number | null;
  created_at: string;
  last_played_at: string | null;
}

export interface TrackCreate {
  title: string;
  artist?: string | null;
  album?: string | null;
  source_type: SourceType;
  source_uri: string;
  folder_id?: number | null;
}

export interface TrackUpdate {
  title?: string;
  artist?: string | null;
  album?: string | null;
  folder_id?: number | null;
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
  folder_id?: number | null;
  created_at: string;
  last_played_at: string | null;
}

export interface StreamCreate {
  title: string;
  artist?: string | null;
  source_uri: string;
  folder_id?: number | null;
}

export interface StreamUpdate {
  title?: string;
  artist?: string | null;
  source_uri?: string;
  folder_id?: number | null;
}

export interface StreamFolder {
  id: number;
  name: string;
  parent_id: number | null;
  created_at: string;
  updated_at: string | null;
}

export interface StreamFolderCreate {
  name: string;
  parent_id?: number | null;
}

export interface StreamFolderUpdate {
  name?: string;
  parent_id?: number | null;
}

// ============================================================================
// Podcasts
// ============================================================================

export interface Podcast {
  id: number;
  podcast_id: number;
  title: string;
  rss_url: string;
  description: string | null;
  cover_art_url: string | null;
  folder_id?: number | null;
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
  folder_id?: number | null;
}

export interface PodcastUpdate {
  title?: string;
  rss_url?: string;
  description?: string | null;
  cover_art_url?: string | null;
  folder_id?: number | null;
}

export interface PodcastFolder {
  id: number;
  name: string;
  parent_id: number | null;
  created_at: string;
  updated_at: string | null;
}

export interface PodcastFolderCreate {
  name: string;
  parent_id?: number | null;
}

export interface PodcastFolderUpdate {
  name?: string;
  parent_id?: number | null;
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

/**
 * One rung of the sound-repair chain (docs/services/Offene-Punkte.md 1.7).
 *
 * `id` is what the dialog translates into a sentence. `detail` is technical
 * wording for the debug export and is never shown: the user sees no sink
 * names, no role names and no stream indices.
 */
export interface AudioTroubleshootStep {
  id: string;
  ok: boolean;
  fixed: boolean;
  detail?: string | null;
}

export interface AudioTroubleshootResult {
  steps: AudioTroubleshootStep[];
  /** Step ids that were actually repaired, bottom of the chain first. */
  fixed: string[];
  /** The one the dialog names as the cause; null when nothing was wrong. */
  cause: string | null;
  tone_played: boolean;
  /** False when the host-helper is missing: steps 1 and 7 were skipped. */
  host_checks_available: boolean;
  timestamp: string;
}

// ============================================================================
// System
// ============================================================================

export interface ServiceStatus {
  service: string;
  state: ServiceState;
  timestamp: string;
  /** Container name, e.g. "minabox-audio". Absent on the probe fallback. */
  container?: string | null;
  /** Version from the image's OCI label; "0.0.0-dev" for a local build. */
  version?: string | null;
  /** Commit the image was built from. */
  git_sha?: string | null;
  build_date?: string | null;
  image?: string | null;
  /** Raw Docker status: running, exited, restarting, ... */
  docker_status?: string | null;
  /** Docker health check result: healthy, unhealthy, starting. */
  health?: string | null;
  /** What the service says about itself in its own /health body. */
  service_status?: 'healthy' | 'degraded' | null;
  restart_count?: number | null;
  started_at?: string | null;
  exit_code?: number | null;
  oom_killed?: boolean | null;
  /** Only on the mqtt entry: whether the backend is attached to the broker. */
  mqtt_connected?: boolean | null;
  cpu_percent?: number | null;
  memory_mb?: number | null;
  memory_percent?: number | null;
}

export interface SystemStatus {
  /**
   * One entry per container that actually exists on this box. Which ones those
   * are depends on COMPOSE_PROFILES, so the list is not a fixed set.
   */
  services: ServiceStatus[];
  device_id: string;
  uptime_seconds?: number | null;
  /** False when the backend cannot reach the Docker socket - then CPU, RAM
   *  and versions of non-Minabox containers are unavailable, not zero. */
  docker_available?: boolean;
  /** False when the kernel's memory cgroup controller is off (the default on
   *  Raspberry Pi OS). No per-container RAM figure exists at all then. */
  memory_stats_available?: boolean;
}

// ============================================================================
// Config: Audio
// ============================================================================

// Hinweis: `id` ist der PulseAudio-Sink-Name (identisch mit `alsa_device`).
// Der audio-service liefert kein separates `sink_name`-Feld.
export interface AudioDeviceItem {
  id: string;
  name: string;
  card_name: string;
  alsa_device?: string;
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
  min_volume?: number;
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
  /** Only for 'pulse': how long the LED stays on per pulse (ms). */
  duration_ms?: number | null;
  /** Only for 'blink': toggle interval (ms). */
  interval_ms?: number | null;
  /** Number of repetitions; 0 or null = infinite. Not used for 'solid' or 'off'. */
  repeat?: number | null;
  /** Only for 'glow': duration of one full breath cycle (dark→bright→dark) in ms. Min 500, default 2000. */
  cycle_ms?: number | null;
  /** Only for 'glow': minimum brightness 0.0–1.0. Default 0.0. */
  min_brightness?: number | null;
  /** Only for 'glow': maximum brightness 0.0–1.0. Default 1.0. */
  max_brightness?: number | null;
}

export interface LED {
  id: string;
  name: string;
  gpio: number;
  bindings: Record<string, LEDPattern>;
  /** When false, LED ignores all state changes and stays off */
  enabled?: boolean;
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
  /** When false, button fires no MQTT action (raw-event still published for test-mode) */
  enabled?: boolean;
}

// ============================================================================
// Config: Display (OLED)
// ============================================================================

/**
 * The display used to be configured as a layout - nine element types, three
 * areas, an order and a font. Every state of the box has a screen of its own
 * now, and each screen picks its own sizes, so all of that stopped reaching
 * the panel. The display service ignores those keys; nothing here sends them.
 */
/** Panel brightness, and the window in which the box turns itself down. */
export interface DisplayBrightness {
  /** Contrast by day, 0-255. */
  day: number;
  /** Contrast at night, 0-255. */
  night: number;
  /** Start of night, HH:MM. */
  night_from: string;
  /** End of night, HH:MM. */
  night_to: string;
  /** Switch the panel off at night while nothing is happening. */
  off_at_night: boolean;
}

export interface DisplayConfig {
  enabled: boolean;
  i2c_bus: number;
  i2c_address: number;
  brightness?: DisplayBrightness;
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

/** Was passiert, wenn der letzte Titel einer Karte durchgelaufen ist. */
export type PlaybackEndBehavior = 'stop' | 'repeat' | 'repeat_while_tag';

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
  /** Resume playback from last saved position when tag is placed back on reader. */
  resume_on_tag_rescan?: boolean;
  playback_end_behavior?: PlaybackEndBehavior;
  /** Minutes of continuous repetition before the box fades out; 0 = no limit. */
  playback_loop_guard_minutes?: number;
  /** Play a playlist in random order. Default true, which is what the box always did. */
  playlist_shuffle?: boolean;
  /** True once the setup wizard has been completed (or explicitly dismissed). */
  setup_completed?: boolean;
  /** Version of the wizard that was completed; lets a later release offer it again. */
  setup_version?: number;
  /** Periodic background scan for updates; shows a header hint when one is ready. */
  auto_update_check_enabled?: boolean;
  /** Largest audio upload accepted over the web UI, in MB. Applied without a restart. */
  max_upload_size_mb?: number;
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
  | 'audio_config'
  | 'rfid_scanned'
  | 'rfid_scanned_learning'
  | 'rfid_removed'
  | 'tag_not_found'
  | 'tag_blocked'
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

/** Emitted when a disabled/blocked tag is placed on the reader */
export interface TagBlockedMessage extends WebSocketMessage {
  type: 'tag_blocked';
  data: {
    tag_id: string;
    name: string | null;
    timestamp: string;
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
