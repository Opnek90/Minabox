import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { MediaFab } from './MediaFab';

let mediaDownloaderInstalled = true;

vi.mock('@/contexts/CapabilitiesContext', () => ({
  useFeatureInstalled: (key: string) =>
    key === 'media_downloader' ? mediaDownloaderInstalled : true,
}));
vi.mock('@/hooks/useAudioStatus', () => ({ useAudioStatus: () => null }));
vi.mock('@/hooks/useLayout', () => ({ useLayout: () => ({ isMobile: false }) }));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'de' } }),
}));

const noop = () => undefined;

const renderFab = () =>
  render(
    <MediaFab
      tab="tracks"
      onCreatePlaylist={noop}
      onCreateFolder={noop}
      onUpload={noop}
      onRecord={noop}
      onRemoteTrack={noop}
      onImport={noop}
      onCreateStream={noop}
      onCreateStreamFolder={noop}
      onCreatePodcast={noop}
      onCreatePodcastFolder={noop}
    />,
  );

describe('MediaFab - URL import hangs off the media downloader (#132)', () => {
  beforeEach(() => {
    mediaDownloaderInstalled = true;
  });

  it('shows "Import from URL" when the media downloader is installed', async () => {
    renderFab();
    await userEvent.click(screen.getByRole('button', { name: 'fab.aria_label' }));
    expect(screen.getByText('tracks.import_from_url')).toBeInTheDocument();
    // Remote-Track (Stream-URL) ist unabhaengig davon immer da.
    expect(screen.getByText('tracks.add_remote')).toBeInTheDocument();
  });

  it('hides "Import from URL" when it is missing - remote track stays', async () => {
    mediaDownloaderInstalled = false;
    renderFab();
    await userEvent.click(screen.getByRole('button', { name: 'fab.aria_label' }));
    expect(screen.queryByText('tracks.import_from_url')).not.toBeInTheDocument();
    expect(screen.getByText('tracks.add_remote')).toBeInTheDocument();
    expect(screen.getByText('tracks.upload')).toBeInTheDocument();
    // Recording needs no add-on either - it is the browser's microphone.
    expect(screen.getByText('tracks.record')).toBeInTheDocument();
  });
});
