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

  it('uebernimmt die Server-Antwort und merkt sie in localStorage', async () => {
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

  it('bleibt fail-open, wenn der Abruf scheitert', async () => {
    get.mockRejectedValue(new Error('network'));
    renderProbe();

    // Kein Feature verschwindet nur wegen eines Fetch-Fehlers.
    await waitFor(() => expect(get).toHaveBeenCalled());
    expect(screen.getByTestId('rfid')).toHaveTextContent('true');
    expect(screen.getByTestId('media')).toHaveTextContent('true');
  });

  it('hydriert synchron aus dem localStorage-Cache (kein Flackern)', () => {
    localStorage.setItem(
      'minabox.capabilities',
      JSON.stringify({ ...ALL_ON, rfid: { installed: false, running: false, healthy: false } }),
    );
    // Abruf haengt - der erste Frame muss trotzdem schon den Cache zeigen.
    get.mockReturnValue(new Promise(() => {}));
    renderProbe();

    expect(screen.getByTestId('rfid')).toHaveTextContent('false');
    expect(screen.getByTestId('media')).toHaveTextContent('true');
  });
});
