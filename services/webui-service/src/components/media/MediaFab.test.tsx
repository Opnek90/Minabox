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
      activeTab={1}
      onCreatePlaylist={noop}
      onCreateFolder={noop}
      onUpload={noop}
      onRemoteTrack={noop}
      onImport={noop}
      onCreateStream={noop}
      onCreateStreamFolder={noop}
      onCreatePodcast={noop}
      onCreatePodcastFolder={noop}
    />,
  );

describe('MediaFab – URL-Import haengt am Media-Downloader (#132)', () => {
  beforeEach(() => {
    mediaDownloaderInstalled = true;
  });

  it('zeigt „Von URL importieren", wenn der Media-Downloader installiert ist', async () => {
    renderFab();
    await userEvent.click(screen.getByRole('button', { name: 'fab.aria_label' }));
    expect(screen.getByText('tracks.import_from_url')).toBeInTheDocument();
    // Remote-Track (Stream-URL) ist unabhaengig davon immer da.
    expect(screen.getByText('tracks.add_remote')).toBeInTheDocument();
  });

  it('blendet „Von URL importieren" aus, wenn er fehlt - Remote-Track bleibt', async () => {
    mediaDownloaderInstalled = false;
    renderFab();
    await userEvent.click(screen.getByRole('button', { name: 'fab.aria_label' }));
    expect(screen.queryByText('tracks.import_from_url')).not.toBeInTheDocument();
    expect(screen.getByText('tracks.add_remote')).toBeInTheDocument();
    expect(screen.getByText('tracks.upload')).toBeInTheDocument();
  });
});
