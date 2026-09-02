import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import deAdmin from '../../../../public/locales/de/admin.json';
import deCommon from '../../../../public/locales/de/common.json';
import { ComponentsBlock } from './ComponentsBlock';

/**
 * The catalogue of optional components (#180, #181).
 *
 * The things worth pinning down are the ones a user notices: a switch is a
 * wish until "apply" - flipping it must not restart anything by itself - a
 * selection that matches what the box already has must not start a run at all,
 * and a component this box does *not* have is still described well enough to
 * decide on it.
 */

const showSuccess = vi.fn();
const showError = vi.fn();

const get = vi.fn();
const put = vi.fn();
const getStatus = vi.fn();
const refreshCapabilities = vi.fn();

vi.mock('@/api/components', () => ({
  PROFILE_FEATURE: {
    rfid: 'rfid',
    led: 'led',
    button: 'button',
    display: 'display',
    media: 'media_downloader',
  },
  // The real one - it decides which language of a catalogue text is shown,
  // and mocking that away would test nothing.
  pickText: (text: Record<string, string> | null, language: string) =>
    text ? (text[language.slice(0, 2)] ?? text.en ?? text.de) : undefined,
  componentsApi: {
    get: (...a: unknown[]) => get(...a),
    put: (...a: unknown[]) => put(...a),
    getStatus: (...a: unknown[]) => getStatus(...a),
  },
}));

vi.mock('@/contexts/CapabilitiesContext', () => ({
  useCapabilities: () => ({
    capabilities: {
      rfid: { installed: true, running: true, healthy: true },
      led: { installed: false, running: false, healthy: false },
      button: { installed: false, running: false, healthy: false },
      display: { installed: false, running: false, healthy: false },
      media_downloader: { installed: false, running: false, healthy: false },
    },
    loading: false,
    refresh: (...a: unknown[]) => refreshCapabilities(...a),
  }),
}));

vi.mock('@/contexts/ToastContext', () => ({
  useToast: () => ({
    showToast: vi.fn(),
    showSuccess: (...a: unknown[]) => showSuccess(...a),
    showError: (...a: unknown[]) => showError(...a),
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
  // The namespace of the call matters here: ConfirmDialog asks for `common`
  // once, without repeating it per key.
  useTranslation: (ns?: string) => ({
    t: (key: string, options?: Record<string, unknown>) => {
      const wanted = (options?.ns as string | undefined) ?? ns ?? 'admin';
      const bundle = wanted === 'common' ? deCommon : deAdmin;
      const hit = lookup(bundle, key) ?? key;
      return ['names', 'text', 'version'].reduce(
        (acc, name) =>
          typeof options?.[name] === 'string'
            ? acc.replace(`{{${name}}}`, options[name] as string)
            : acc,
        hit,
      );
    },
    i18n: { language: 'de', changeLanguage: vi.fn() },
  }),
}));

const text = (key: string): string => {
  const hit = lookup(deAdmin, key);
  if (hit === undefined) throw new Error(`missing locale key: ${key}`);
  return hit;
};
const commonText = (key: string): string => {
  const hit = lookup(deCommon, key);
  if (hit === undefined) throw new Error(`missing common locale key: ${key}`);
  return hit;
};

/** One catalogue entry as the backend sends it. */
const entry = (
  profile: string,
  service: string,
  installed: boolean,
  extra: Record<string, unknown> = {},
) => ({
  profile,
  service,
  installed,
  summary: { de: `Was ${profile} tut`, en: `What ${profile} does` },
  hardware: null,
  network: false,
  running: installed,
  healthy: installed,
  version: installed ? '0.2.4' : null,
  latest: '0.2.4',
  ...extra,
});

/** A box that was installed with the card reader only. */
const BOX = {
  components: [
    entry('rfid', 'rfid', true, {
      hardware: { de: 'PN532 am I2C', en: 'A PN532 on I2C' },
    }),
    entry('led', 'led', false),
    entry('button', 'button', false),
    entry('display', 'display', false),
    entry('media', 'media-downloader', false, { network: true }),
  ],
  profiles: ['rfid'],
  channel: 'stable',
  busy: false,
};

describe('ComponentsBlock', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    get.mockResolvedValue(BOX);
    put.mockResolvedValue({
      ok: true,
      changed: true,
      profiles: ['rfid', 'led'],
      reboot_required: false,
      blocked: [],
      steps: [],
    });
    getStatus.mockResolvedValue({
      running: false,
      step: 4,
      step_count: 4,
      step_key: 'verify',
      exit_code: 0,
      steps: [],
      log: 'done',
      profiles: ['rfid', 'led'],
      reboot_required: false,
      blocked: [],
    });
  });

  it('leaves the box alone until the change is applied', async () => {
    const user = userEvent.setup();
    render(<ComponentsBlock />);

    const apply = await screen.findByRole('button', { name: text('system.components_apply') });
    // Nothing changed yet, so there is nothing to apply.
    expect(apply).toBeDisabled();

    await user.click(screen.getByRole('checkbox', { name: /LEDs/ }));
    expect(apply).toBeEnabled();
    // A flipped switch is a wish - the box is only touched on confirm.
    expect(put).not.toHaveBeenCalled();

    await user.click(apply);
    const dialog = await screen.findByRole('dialog');
    // The question says which component is about to be switched on.
    expect(dialog).toHaveTextContent(
      text('system.components_confirm_on').replace('{{names}}', text('system.component_led')),
    );
    await user.click(
      within(dialog).getByRole('button', { name: commonText('actions.confirm') }),
    );

    await waitFor(() => expect(put).toHaveBeenCalledWith(['rfid', 'led']));
    await waitFor(() => expect(showSuccess).toHaveBeenCalledWith(text('system.components_success')));
    // The backend was recreated with the new profiles, so what the rest of the
    // UI may show has changed too.
    await waitFor(() => expect(refreshCapabilities).toHaveBeenCalled());
  });

  it('tells the version list to re-read after a run', async () => {
    // The list above is one row per existing container, and it reads once on
    // mount. Without this the row of a component that is gone would stay on
    // screen until someone reloads the page.
    const onChanged = vi.fn();
    const user = userEvent.setup();
    render(<ComponentsBlock onChanged={onChanged} />);

    const apply = await screen.findByRole('button', { name: text('system.components_apply') });
    await user.click(screen.getByRole('checkbox', { name: /LEDs/ }));
    await user.click(apply);
    const dialog = await screen.findByRole('dialog');
    await user.click(
      within(dialog).getByRole('button', { name: commonText('actions.confirm') }),
    );

    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });

  it('picks up a change that was already running', async () => {
    // The run recreates the backend, so a page that comes back mid-run is not
    // an edge case. Without this it would show switches that do nothing.
    get.mockResolvedValue({ ...BOX, busy: true });
    getStatus.mockResolvedValue({
      running: true,
      step: 2,
      step_count: 4,
      step_key: 'pull',
      exit_code: null,
      steps: [],
      log: '',
      profiles: ['rfid', 'led'],
      reboot_required: false,
      blocked: [],
    });
    render(<ComponentsBlock />);

    await screen.findByRole('dialog');
    await waitFor(() => expect(getStatus).toHaveBeenCalled());
    // Nothing was started from here - it was already going.
    expect(put).not.toHaveBeenCalled();
  });

  it('describes a component this box does not have', async () => {
    // The catalogue is what makes a component findable without the
    // documentation: what it does, what it needs, and what would be installed.
    render(<ComponentsBlock />);

    expect(await screen.findByText('Was media tut')).toBeInTheDocument();
    expect(screen.getByText(text('system.components_needs_network'))).toBeInTheDocument();
    // Four components are not installed here, and each names what adding it
    // would bring.
    expect(
      screen.getAllByText(
        text('system.components_version_available').replace('{{version}}', '0.2.4'),
      ),
    ).toHaveLength(4);
    // And for the one that is installed: what it needs on the box, and what
    // is running there.
    expect(
      screen.getByText(
        text('system.components_needs_hardware').replace('{{text}}', 'PN532 am I2C'),
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(text('system.components_version').replace('{{version}}', '0.2.4')),
    ).toBeInTheDocument();
  });

  it('does not restart anything for a selection the box already has', async () => {
    // The box answers "nothing changed" - that must not open a progress window
    // or report a run that never happened.
    put.mockResolvedValue({
      ok: true,
      changed: false,
      profiles: ['rfid'],
      reboot_required: false,
      blocked: [],
      steps: [],
    });
    const user = userEvent.setup();
    render(<ComponentsBlock />);

    const apply = await screen.findByRole('button', { name: text('system.components_apply') });
    const led = screen.getByRole('checkbox', { name: /LEDs/ });
    await user.click(led);
    await user.click(led);
    expect(apply).toBeDisabled();

    expect(getStatus).not.toHaveBeenCalled();
    expect(showSuccess).not.toHaveBeenCalled();
  });
});
