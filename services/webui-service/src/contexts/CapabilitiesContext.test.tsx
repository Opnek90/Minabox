import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { CapabilitiesProvider, useFeatureInstalled } from './CapabilitiesContext';

const get = vi.fn();

vi.mock('@/api/capabilities', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/capabilities')>();
  return { ...actual, capabilitiesApi: { get: () => get() } };
});

const Probe = () => (
  <>
    <span data-testid="rfid">{String(useFeatureInstalled('rfid'))}</span>
    <span data-testid="media">{String(useFeatureInstalled('media_downloader'))}</span>
  </>
);

const renderProbe = () =>
  render(
    <CapabilitiesProvider>
      <Probe />
    </CapabilitiesProvider>,
  );

const ALL_ON = {
  rfid: { installed: true, running: true, healthy: true },
  led: { installed: true, running: true, healthy: true },
  button: { installed: true, running: true, healthy: true },
  display: { installed: true, running: true, healthy: true },
  media_downloader: { installed: true, running: true, healthy: true },
};

describe('CapabilitiesContext', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });
  afterEach(() => {
    localStorage.clear();
  });

  it('takes the server response and remembers it in localStorage', async () => {
    get.mockResolvedValue({
      ...ALL_ON,
      media_downloader: { installed: false, running: false, healthy: false },
    });
    renderProbe();

    await waitFor(() => expect(screen.getByTestId('media')).toHaveTextContent('false'));
    expect(screen.getByTestId('rfid')).toHaveTextContent('true');
    expect(JSON.parse(localStorage.getItem('minabox.capabilities')!).media_downloader.installed).toBe(
      false,
    );
  });

  it('stays fail-open when the fetch fails', async () => {
    get.mockRejectedValue(new Error('network'));
    renderProbe();

    // No feature disappears just because of a fetch error.
    await waitFor(() => expect(get).toHaveBeenCalled());
    expect(screen.getByTestId('rfid')).toHaveTextContent('true');
    expect(screen.getByTestId('media')).toHaveTextContent('true');
  });

  it('hydrates synchronously from the localStorage cache (no flicker)', () => {
    localStorage.setItem(
      'minabox.capabilities',
      JSON.stringify({ ...ALL_ON, rfid: { installed: false, running: false, healthy: false } }),
    );
    // The fetch hangs - the first frame must still already show the cache.
    get.mockReturnValue(new Promise(() => {}));
    renderProbe();

    expect(screen.getByTestId('rfid')).toHaveTextContent('false');
    expect(screen.getByTestId('media')).toHaveTextContent('true');
  });
});
