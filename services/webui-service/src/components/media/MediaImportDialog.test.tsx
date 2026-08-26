import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import deCommon from '../../../public/locales/de/common.json';
import deMedia from '../../../public/locales/de/media.json';
import { MediaImportDialog } from './MediaImportDialog';

/**
 * Der Dialog verlangt eine ausdrueckliche Bestaetigung zur rechtmaessigen
 * Nutzung, bevor eine URL geprueft oder importiert werden kann. Die Tests
 * pinnen genau diese Gate-Logik – ohne Haken darf keine der beiden Aktionen
 * erreichbar sein, und ein erneut geoeffneter Dialog faengt wieder bei null an.
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

// Uebersetzt gegen die echten Locale-Dateien, damit ein fehlender oder
// umbenannter Key den Test kippen laesst und nicht still durchrutscht.
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

describe('MediaImportDialog – Bestaetigung zur rechtmaessigen Nutzung', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('zeigt den Hinweis mit einer standardmaessig leeren Checkbox', () => {
    renderDialog();

    expect(screen.getByText(text('media_import.disclaimer_title'))).toBeInTheDocument();
    expect(screen.getByText(text('media_import.disclaimer_body'))).toBeInTheDocument();
    expect(confirmCheckbox()).not.toBeChecked();
  });

  it('haelt Pruefen und Importieren ohne Bestaetigung deaktiviert – auch mit URL', async () => {
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

  it('startet den Import erst nach der Bestaetigung', async () => {
    const user = userEvent.setup();
    fromUrl.mockResolvedValue({ track_id: 7, status: 'pending' });
    renderDialog();

    await user.type(screen.getByLabelText(text('media_import.url_label')), 'https://example.org/media');
    await user.click(confirmCheckbox());
    await user.click(importButton());

    await waitFor(() => expect(fromUrl).toHaveBeenCalledTimes(1));
    expect(fromUrl.mock.calls[0][0]).toBe('https://example.org/media');
  });

  it('nimmt die Bestaetigung beim erneuten Oeffnen wieder zurueck', async () => {
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
  it('zeigt die gemeldete Import-Stufe an, nicht nur einen Spinner', async () => {
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
    expect(screen.getByText(text('media_import.stage_finalizing'))).toBeInTheDocument();
    expect(screen.getByText(text('media_import.stage_saving'))).toBeInTheDocument();
  }, 8000);

  it('haengt den Prozentsatz an, solange die Stufe "downloading" laeuft', async () => {
    const user = userEvent.setup();
    fromUrl.mockResolvedValue({ track_id: 7, status: 'pending' });
    getDownloadStatus.mockResolvedValue({
      track_id: 7,
      status: 'downloading',
      error: null,
      stage: 'downloading',
      percent: 42.3,
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
  }, 8000);

  it('verknuepft die Checkbox mit dem Hilfetext, solange nicht bestaetigt ist', async () => {
    const user = userEvent.setup();
    renderDialog();

    const hint = screen.getByText(text('media_import.confirm_hint'));
    expect(confirmCheckbox()).toHaveAccessibleDescription(text('media_import.confirm_hint'));

    await user.click(confirmCheckbox());

    expect(hint).not.toBeInTheDocument();
    expect(confirmCheckbox()).not.toHaveAttribute('aria-describedby');
  });
});
