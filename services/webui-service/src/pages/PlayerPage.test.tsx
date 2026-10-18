import { act, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { PlayerPage } from './PlayerPage';
import { wsEventTarget, WS_EVENT_MESSAGE } from '@/contexts/WebSocketContext';
import type { AudioStatus } from '@/types/api';

const BASE_STATUS: AudioStatus = {
  state: 'stopped',
  track_id: null,
  track_title: null,
  track_artist: null,
  track_album: null,
  track_cover_art_url: null,
  source_type: null,
  source_uri: null,
  position_ms: 0,
  duration_ms: null,
  volume: 50,
  timestamp: '2026-10-18T12:00:00Z',
};

let currentStatus: AudioStatus = { ...BASE_STATUS };

const getSessionMock = vi.fn();

vi.mock('@/hooks/useAudioStatus', () => ({
  useAudioStatus: () => currentStatus,
}));

vi.mock('@/hooks/useSleepTimer', () => ({
  useSleepTimer: () => null,
}));

vi.mock('@/contexts/WebSocketContext', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/contexts/WebSocketContext')>();
  return {
    ...actual,
    useWebSocket: () => ({
      isConnected: true,
      sleepTimerStatus: null,
      cachedAudioStatus: null,
      lastMessage: null,
      sendMessage: vi.fn(),
    }),
  };
});

vi.mock('@/api/audio', () => ({
  audioApi: {
    getSession: () => getSessionMock(),
    getDevices: () => Promise.resolve({ devices: [] }),
    play: vi.fn(),
    pause: vi.fn(),
    stop: vi.fn(),
    next: vi.fn(),
    previous: vi.fn(),
    seek: vi.fn(),
    setVolume: vi.fn(),
    startSleepTimer: vi.fn(),
    cancelSleepTimer: vi.fn(),
    switchDevice: vi.fn(),
    setRepeatMode: vi.fn(),
    setShuffle: vi.fn(),
  },
}));

vi.mock('@/api/config', () => ({
  configApi: {
    getAudio: () => Promise.resolve({ min_volume: 0, max_volume: 100, default_volume: 50 }),
  },
}));

describe('PlayerPage repeat/shuffle visibility', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    currentStatus = { ...BASE_STATUS };
    getSessionMock.mockResolvedValue({
      queue: [],
      repeat_mode: 'all',
      shuffle: true,
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('shows repeat and shuffle buttons immediately when transitioning from stopped to playing within staleTime', async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    const { rerender } = render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <PlayerPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    // While stopped, repeat and shuffle are not shown.
    expect(screen.queryByRole('button', { name: 'player.repeat_all' })).not.toBeInTheDocument();

    // Start playing within the 10s staleTime window right after being stopped.
    currentStatus = {
      ...currentStatus,
      state: 'playing',
      track_id: 42,
      track_title: 'Test Song',
      duration_ms: 120000,
    };

    rerender(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <PlayerPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    const repeatBtn = screen.getByRole('button', { name: 'player.repeat_all' });
    const shuffleBtn = screen.getByRole('button', { name: 'player.shuffle_on' });
    expect(repeatBtn).toBeInTheDocument();
    expect(shuffleBtn).toBeInTheDocument();

    await waitFor(() => expect(getSessionMock).toHaveBeenCalled());
    await waitFor(() => expect(repeatBtn).toHaveAttribute('aria-pressed', 'true'));
    expect(shuffleBtn).toHaveAttribute('aria-pressed', 'true');

    // WebSocket repeat_mode update is reflected without reload.
    act(() => {
      wsEventTarget.dispatchEvent(
        new CustomEvent(WS_EVENT_MESSAGE, {
          detail: { type: 'repeat_mode', data: { repeat_mode: 'none' } },
        }),
      );
    });

    await waitFor(() => expect(repeatBtn).toHaveAttribute('aria-pressed', 'false'));
  });
});
