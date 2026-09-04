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

const renderFab = (tab: 'tracks' | 'overview' = 'tracks') =>
  render(
    <MediaFab
      tab={tab}
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

describe('MediaFab - the overview creates in all four areas', () => {
  beforeEach(() => {
    mediaDownloaderInstalled = true;
  });

  it('offers every create action there, and no folder action', async () => {
    renderFab('overview');
    await userEvent.click(screen.getByRole('button', { name: 'fab.aria_label' }));

    for (const action of [
      'playlists.add_playlist',
      'tracks.upload',
      'tracks.record',
      'tracks.import_from_url',
      'tracks.add_remote',
      'tracks.add_stream',
      'podcasts.add',
    ]) {
      expect(screen.getByText(action)).toBeInTheDocument();
    }
    // A folder belongs to the tree of one tab, and the overview has none.
    expect(screen.queryByText('folders.new')).not.toBeInTheDocument();
  });

  it('drops the URL import there too when the media downloader is missing', async () => {
    mediaDownloaderInstalled = false;
    renderFab('overview');
    await userEvent.click(screen.getByRole('button', { name: 'fab.aria_label' }));

    expect(screen.queryByText('tracks.import_from_url')).not.toBeInTheDocument();
    expect(screen.getByText('tracks.record')).toBeInTheDocument();
  });
});
