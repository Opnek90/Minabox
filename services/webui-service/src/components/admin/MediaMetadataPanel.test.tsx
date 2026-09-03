import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { MediaMetadataPanel } from './MediaMetadataPanel';
import type { MetadataBackfillStatus } from '@/types/api';

const idle: MetadataBackfillStatus = {
  running: false,
  total: 0,
  processed: 0,
  updated: 0,
  online_used: 0,
  finished_at: null,
  error: null,
};

const backfillMetadata = vi.fn().mockResolvedValue(undefined);
const getBackfillStatus = vi.fn().mockResolvedValue(idle);

vi.mock('@/api/tracks', () => ({
  tracksApi: {
    backfillMetadata: () => backfillMetadata(),
    getBackfillStatus: () => getBackfillStatus(),
  },
}));
vi.mock('@/contexts/ToastContext', () => ({
  useToast: () => ({ showError: vi.fn(), showSuccess: vi.fn() }),
}));
vi.mock('@/utils/apiError', () => ({ translateApiError: () => 'error' }));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'en' } }),
}));

describe('MediaMetadataPanel', () => {
  beforeEach(() => {
    backfillMetadata.mockClear();
    getBackfillStatus.mockClear();
  });

  it('reads the current backfill status on mount', async () => {
    // A run started in another tab (or still going from a previous visit) has
    // to show up here too.
    render(<MediaMetadataPanel />);
    await waitFor(() => expect(getBackfillStatus).toHaveBeenCalled());
  });

  it('does not carry a switch for the addon itself', async () => {
    // Whether the box may ask MusicBrainz is the addon, and its switch is the
    // row in the addons table. A second one here would be two switches for one
    // setting on two pages.
    render(<MediaMetadataPanel />);
    await waitFor(() => expect(getBackfillStatus).toHaveBeenCalled());
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
  });

  it('starts the backfill when the button is pressed', async () => {
    const user = userEvent.setup();
    render(<MediaMetadataPanel />);
    await user.click(screen.getByRole('button', { name: 'general.metadata_backfill_start' }));
    await waitFor(() => expect(backfillMetadata).toHaveBeenCalledTimes(1));
  });
});
