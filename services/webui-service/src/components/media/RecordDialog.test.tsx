import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import deCommon from '../../../public/locales/de/common.json';
import deMedia from '../../../public/locales/de/media.json';
import { RecordDialog } from './RecordDialog';

/**
 * Two paths, and the dialog has to be honest about which one it is on.
 *
 * Over plain http - how the box is reached at home - the browser hands out no
 * microphone at all, and the whole feature would be a dead button. These tests
 * pin that the dialog says so and still leads somewhere (pick a voice memo),
 * and that where recording does work, the duration measured while the
 * microphone was open travels with the upload. That number is not decoration:
 * for a WebM recording it is the only duration the box will ever have.
 */

const upload = vi.fn();

vi.mock('@/api/tracks', () => ({
  tracksApi: { upload: (...args: unknown[]) => upload(...args) },
}));

vi.mock('@/contexts/ToastContext', () => ({
  useToast: () => ({
    showToast: vi.fn(),
    showSuccess: vi.fn(),
    showError: vi.fn(),
    showWarning: vi.fn(),
  }),
}));

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
      return lookup(bundle, key) ?? key;
    },
    i18n: { language: 'de', changeLanguage: vi.fn() },
  }),
}));

const text = (key: string): string => {
  const hit = lookup(deMedia, key);
  if (hit === undefined) throw new Error(`missing locale key: ${key}`);
  return hit;
};

/** A MediaRecorder that emits one chunk and never touches real hardware. */
class FakeMediaRecorder {
  static isTypeSupported = (type: string) => type === 'audio/webm;codecs=opus';
  state: 'inactive' | 'recording' = 'inactive';
  ondataavailable: ((event: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  onerror: (() => void) | null = null;
  readonly mimeType = 'audio/webm;codecs=opus';

  start() {
    this.state = 'recording';
  }

  stop() {
    this.state = 'inactive';
    this.ondataavailable?.({ data: new Blob(['hallo'], { type: this.mimeType }) });
    this.onstop?.();
  }
}

const stopTrack = vi.fn();

/**
 * A clock that advances a full second per reading.
 *
 * The recorder measures with `performance.now()`, and the dialog refuses a
 * take under half a second. Left on the real clock the test would pass or fail
 * depending on how fast the machine got from "start" to "stop" - on a Pi in CI
 * that is exactly the kind of coin flip that makes a suite worthless.
 */
const stubTickingClock = () => {
  let now = 0;
  vi.stubGlobal('performance', { ...performance, now: () => (now += 1000) });
};

/** Put a working microphone stack in place, or take it away entirely. */
const setMicrophone = (available: boolean) => {
  if (available) {
    stubTickingClock();
    vi.stubGlobal('MediaRecorder', FakeMediaRecorder);
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [{ stop: stopTrack }] }) },
    });
  } else {
    vi.stubGlobal('MediaRecorder', undefined);
    Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: undefined });
  }
};

const renderDialog = () =>
  render(<RecordDialog open onClose={vi.fn()} onSuccess={vi.fn()} />);

beforeEach(() => {
  vi.clearAllMocks();
  upload.mockResolvedValue({ id: 7, title: 'Gute Nacht' });
  // jsdom has no object URLs; the preview player only needs a string. Set on
  // URL itself rather than stubbed: `vi.unstubAllGlobals()` runs before the
  // testing-library cleanup and would take revokeObjectURL away again just as
  // the unmounting dialog calls it.
  URL.createObjectURL = () => 'blob:test';
  URL.revokeObjectURL = () => undefined;
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('RecordDialog - without a microphone API', () => {
  beforeEach(() => setMicrophone(false));

  it('explains why and offers the file instead of a dead button', () => {
    renderDialog();

    expect(screen.getByText(text('record.insecure_title'))).toBeInTheDocument();
    expect(screen.getByText(text('record.insecure_body'))).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: text('record.start') })).not.toBeInTheDocument();
    expect(screen.getByText(text('record.pick_file'))).toBeInTheDocument();
  });

  it('uploads a picked voice memo without inventing a duration', async () => {
    const user = userEvent.setup();
    renderDialog();

    // The dialog renders through a portal, so the input is not under the
    // render container.
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, new File(['x'], 'Sprachmemo.m4a', { type: 'audio/mp4' }));
    await user.click(screen.getByRole('button', { name: text('record.save') }));

    await waitFor(() => expect(upload).toHaveBeenCalled());
    const [file, metadata] = upload.mock.calls[0];
    expect(file.name).toBe('Sprachmemo.m4a');
    // The title was taken from the file name, and no duration was guessed.
    expect(metadata.title).toBe('Sprachmemo');
    expect(metadata.durationMs).toBeUndefined();
  });
});

describe('RecordDialog - with a microphone', () => {
  beforeEach(() => setMicrophone(true));

  it('records, releases the microphone and sends the measured duration', async () => {
    const user = userEvent.setup();
    renderDialog();

    await user.click(screen.getByRole('button', { name: text('record.start') }));
    const stopButton = await screen.findByRole('button', { name: text('record.stop') });
    await user.click(stopButton);

    // The take is there and can be discarded, and nothing keeps the
    // microphone open once the recorder stopped.
    await screen.findByRole('button', { name: text('record.again') });
    expect(stopTrack).toHaveBeenCalled();

    await user.type(screen.getByLabelText(`${text('record.fields.title')} *`), 'Gute Nacht');
    await user.click(screen.getByRole('button', { name: text('record.save') }));

    await waitFor(() => expect(upload).toHaveBeenCalled());
    const [file, metadata] = upload.mock.calls[0];
    // The extension has to match the container the browser really produced -
    // the backend names the stored file after it.
    expect(file.name).toBe('message.webm');
    expect(metadata.title).toBe('Gute Nacht');
    expect(metadata.durationMs).toBeGreaterThanOrEqual(1000);
  });

  it('keeps saving out of reach until there is something to save', () => {
    renderDialog();

    expect(screen.getByRole('button', { name: text('record.save') })).toBeDisabled();
  });

  it('refuses a take that was over before it began', async () => {
    // A slip of the finger on the record button: start and stop land in the
    // same millisecond, and half a second of silence is not a message.
    vi.stubGlobal('performance', { ...performance, now: () => 0 });
    const user = userEvent.setup();
    renderDialog();

    await user.click(screen.getByRole('button', { name: text('record.start') }));
    await user.click(await screen.findByRole('button', { name: text('record.stop') }));

    expect(await screen.findByText(text('record.too_short'))).toBeInTheDocument();
    expect(screen.getByRole('button', { name: text('record.save') })).toBeDisabled();
  });
});
