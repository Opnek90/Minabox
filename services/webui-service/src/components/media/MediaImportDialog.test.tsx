import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import deCommon from '../../../public/locales/de/common.json';
import deMedia from '../../../public/locales/de/media.json';
import { MediaImportDialog } from './MediaImportDialog';

/**
 * The dialog requires an explicit confirmation of lawful use before a URL can
 * be checked or imported. The tests pin exactly this gate logic - without the
 * checkbox neither action may be reachable, and a re-opened dialog starts from
 * zero again.
 */

const validateUrl = vi.fn();
const fromUrl = vi.fn();
const getById = vi.fn();
const getDownloadStatus = vi.fn();

vi.mock('@/api/tracks', () => ({
  tracksApi: {
    validateUrl: (...args: unknown[]) => validateUrl(...args),
    fromUrl: (...args: unknown[]) => fromUrl(...args),
    getById: (...args: unknown[]) => getById(...args),
    getDownloadStatus: (...args: unknown[]) => getDownloadStatus(...args),
  },
}));

vi.mock('@/contexts/ToastContext', () => ({
  useToast: () => ({
    showToast: vi.fn(),
    showSuccess: vi.fn(),
    showError: vi.fn(),
    showWarning: vi.fn(),
  }),
}));

// Translated against the real locale files, so a missing or renamed key fails
// the test instead of slipping through silently.
const lookup = (bundle: unknown, key: string): string | undefined => {
  const value = key
    .split('.')
    .reduce<unknown>(
      (acc, part) =>
        acc && typeof acc === 'object' ? (acc as Record<string, unknown>)[part] : undefined,
      bundle,
    );
  return typeof value === 'string' ? value : undefined;
};

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) => {
      const bundle = options?.ns === 'common' ? deCommon : deMedia;
      const hit = lookup(bundle, key);
      if (hit !== undefined) return hit;
      return typeof options?.defaultValue === 'string' ? options.defaultValue : key;
    },
    i18n: { language: 'de', changeLanguage: vi.fn() },
  }),
}));

const text = (key: string): string => {
  const hit = lookup(deMedia, key);
  if (hit === undefined) throw new Error(`missing locale key: ${key}`);
  return hit;
};

const confirmCheckbox = () => screen.getByRole('checkbox', { name: text('media_import.confirm_label') });
const checkButton = () => screen.getByRole('button', { name: text('media_import.check') });
const importButton = () => screen.getByRole('button', { name: text('media_import.import') });

const renderDialog = (open = true) =>
  render(<MediaImportDialog open={open} onClose={vi.fn()} onSuccess={vi.fn()} />);

describe('MediaImportDialog - confirmation of lawful use', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows the notice with a checkbox that is empty by default', () => {
    renderDialog();

    expect(screen.getByText(text('media_import.disclaimer_title'))).toBeInTheDocument();
    expect(screen.getByText(text('media_import.disclaimer_body'))).toBeInTheDocument();
    expect(confirmCheckbox()).not.toBeChecked();
  });

  it('keeps check and import disabled without confirmation - even with a URL', async () => {
    const user = userEvent.setup();
    renderDialog();

    await user.type(screen.getByLabelText(text('media_import.url_label')), 'https://example.org/media');

    expect(checkButton()).toBeDisabled();
    expect(importButton()).toBeDisabled();
    expect(validateUrl).not.toHaveBeenCalled();
    expect(fromUrl).not.toHaveBeenCalled();
  });

  it('gibt beide Aktionen erst nach dem Setzen des Hakens frei', async () => {
    const user = userEvent.setup();
    renderDialog();

    await user.type(screen.getByLabelText(text('media_import.url_label')), 'https://example.org/media');
    await user.click(confirmCheckbox());

    expect(confirmCheckbox()).toBeChecked();
    expect(checkButton()).toBeEnabled();
    expect(importButton()).toBeEnabled();
  });

  it('starts the import only after confirmation', async () => {
    const user = userEvent.setup();
    fromUrl.mockResolvedValue({ track_id: 7, status: 'pending' });
    renderDialog();

    await user.type(screen.getByLabelText(text('media_import.url_label')), 'https://example.org/media');
    await user.click(confirmCheckbox());
    await user.click(importButton());

    await waitFor(() => expect(fromUrl).toHaveBeenCalledTimes(1));
    expect(fromUrl.mock.calls[0][0]).toBe('https://example.org/media');
  });

  it('resets the confirmation when reopened', async () => {
    const user = userEvent.setup();
    const { rerender } = renderDialog();

    await user.click(confirmCheckbox());
    expect(confirmCheckbox()).toBeChecked();

    rerender(<MediaImportDialog open={false} onClose={vi.fn()} onSuccess={vi.fn()} />);
    rerender(<MediaImportDialog open onClose={vi.fn()} onSuccess={vi.fn()} />);

    await waitFor(() => expect(confirmCheckbox()).not.toBeChecked());
    expect(checkButton()).toBeDisabled();
    expect(importButton()).toBeDisabled();
  });

  // Real POLL_INTERVAL_MS (2s) plus the waitFor budget below exceeds
  // vitest's 5s default test timeout, hence the explicit timeout argument.
  it('shows the reported import stage, not just a spinner', async () => {
    const user = userEvent.setup();
    fromUrl.mockResolvedValue({ track_id: 7, status: 'pending' });
    getDownloadStatus.mockResolvedValue({
      track_id: 7,
      status: 'downloading',
      error: null,
      stage: 'converting',
      percent: null,
    });
    renderDialog();

    await user.type(screen.getByLabelText(text('media_import.url_label')), 'https://example.org/media');
    await user.click(confirmCheckbox());
    await user.click(importButton());

    // fetching_info and downloading are behind us (stage: converting) -
    // their label is still rendered, converting is the active one.
    await waitFor(
      () => expect(screen.getByText(text('media_import.stage_converting'))).toBeInTheDocument(),
      { timeout: 4000 },
    );
    expect(screen.getByText(text('media_import.stage_embedding_thumbnail'))).toBeInTheDocument();
    expect(screen.getByText(text('media_import.stage_embedding_metadata'))).toBeInTheDocument();
    expect(screen.getByText(text('media_import.stage_saving'))).toBeInTheDocument();
  }, 8000);

  it('appends the percentage and speed/ETA while the stage is "downloading"', async () => {
    const user = userEvent.setup();
    fromUrl.mockResolvedValue({ track_id: 7, status: 'pending' });
    getDownloadStatus.mockResolvedValue({
      track_id: 7,
      status: 'downloading',
      error: null,
      stage: 'downloading',
      percent: 42.3,
      speed_bytes_per_sec: 1_258_291, // 1.2 MB/s
      eta_seconds: 5,
    });
    renderDialog();

    await user.type(screen.getByLabelText(text('media_import.url_label')), 'https://example.org/media');
    await user.click(confirmCheckbox());
    await user.click(importButton());

    await waitFor(
      () =>
        expect(
          screen.getByText(`${text('media_import.stage_downloading')} (42%)`),
        ).toBeInTheDocument(),
      { timeout: 4000 },
    );
    // The mocked t() above does plain key lookup, not real interpolation, so
    // this checks the eta key was used and rendered alongside the speed -
    // real {{time}} substitution is i18next's own job, not this dialog's.
    expect(screen.getByText(`1.2 MB/s · ${text('media_import.eta')}`)).toBeInTheDocument();
  }, 8000);

  it('links the checkbox to the help text while not confirmed', async () => {
    const user = userEvent.setup();
    renderDialog();

    const hint = screen.getByText(text('media_import.confirm_hint'));
    expect(confirmCheckbox()).toHaveAccessibleDescription(text('media_import.confirm_hint'));

    await user.click(confirmCheckbox());

    expect(hint).not.toBeInTheDocument();
    expect(confirmCheckbox()).not.toHaveAttribute('aria-describedby');
  });
});
