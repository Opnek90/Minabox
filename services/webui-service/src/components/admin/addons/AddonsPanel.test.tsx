import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import deAdmin from '../../../../public/locales/de/admin.json';
import deCommon from '../../../../public/locales/de/common.json';
import { AddonsPanel } from './AddonsPanel';

/**
 * The addons table (#180, #181).
 *
 * The things worth pinning down are the ones a user notices: the switch of a
 * compose addon is a wish until "apply" - flipping it must not restart
 * anything by itself - a selection that matches what the box already has must
 * not start a run at all, and an addon this box does *not* have is still
 * described well enough to decide on it.
 *
 * Plus the two that came with the addons page: an addon that lives in a
 * setting is written straight away rather than waiting for a run it does not
 * need, and one addon can be updated on its own without dragging the rest of
 * the box along.
 */

const showSuccess = vi.fn();
const showError = vi.fn();

const get = vi.fn();
const put = vi.fn();
const getStatus = vi.fn();
const setSetting = vi.fn();
const startUpdate = vi.fn();
const refreshCapabilities = vi.fn();

vi.mock('@/api/addons', async () => {
  // The real module for everything that decides what is shown - which language
  // of a catalogue text wins, and which kind of addon a row is. Mocking those
  // away would test nothing.
  const actual = await vi.importActual<typeof import('@/api/addons')>('@/api/addons');
  return {
    ...actual,
    addonsApi: {
      get: (...a: unknown[]) => get(...a),
      put: (...a: unknown[]) => put(...a),
      getStatus: (...a: unknown[]) => getStatus(...a),
      setSetting: (...a: unknown[]) => setSetting(...a),
    },
  };
});

vi.mock('@/components/admin/maintenance/useUpdateRun', () => ({
  useUpdateRun: () => ({
    running: false,
    kind: 'update' as const,
    status: null,
    progressOpen: false,
    closeProgress: vi.fn(),
    start: (...a: unknown[]) => startUpdate(...a),
    startRollback: vi.fn(),
  }),
}));

vi.mock('@/contexts/CapabilitiesContext', () => ({
  useCapabilities: () => ({
    capabilities: {
      rfid: { installed: true, running: true, healthy: true },
      led: { installed: false, running: false, healthy: false },
      button: { installed: false, running: false, healthy: false },
      display: { installed: false, running: false, healthy: false },
      media_downloader: { installed: false, running: false, healthy: false },
      voice: { installed: false, running: false, healthy: false },
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
  useTranslation: (ns?: string | string[]) => ({
    t: (key: string, options?: Record<string, unknown>) => {
      const fallback = Array.isArray(ns) ? ns[0] : ns;
      const wanted = (options?.ns as string | undefined) ?? fallback ?? 'admin';
      const bundle = wanted === 'common' ? deCommon : deAdmin;
      const hit = lookup(bundle, key) ?? key;
      return ['names', 'text', 'version', 'name'].reduce(
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

/** Reports the current URL, so a click that should navigate can be checked
 * against it - the gear button is a link now, not a dialog trigger. */
const LocationProbe: React.FC = () => {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}{location.search}</div>;
};

const renderPanel = () =>
  render(
    <MemoryRouter initialEntries={['/admin']}>
      <AddonsPanel />
      <LocationProbe />
    </MemoryRouter>,
  );

/** One compose addon as the backend sends it. */
const entry = (
  id: string,
  service: string,
  installed: boolean,
  extra: Record<string, unknown> = {},
) => ({
  id,
  profile: id,
  service,
  category: 'hardware',
  install: { type: 'profile' },
  settings_section: id,
  installed,
  name: null,
  summary: { de: `Was ${id} tut`, en: `What ${id} does` },
  hardware: null,
  network: false,
  running: installed,
  healthy: installed,
  version: installed ? '0.2.4' : null,
  latest: '0.2.4',
  update_available: false,
  ...extra,
});

/** The addon that is one field of the general settings, not a container. */
const METADATA = {
  id: 'metadata',
  profile: null,
  service: null,
  category: 'software',
  install: { type: 'setting', field: 'online_metadata_lookup_enabled' },
  settings_section: 'media_metadata',
  installed: false,
  name: { de: 'Online-Metadaten', en: 'Online metadata' },
  summary: { de: 'Schlägt Cover nach', en: 'Looks up cover art' },
  hardware: null,
  network: true,
  running: false,
  healthy: false,
  version: null,
  latest: null,
  update_available: false,
};

/** A box that was installed with the card reader only. */
const BOX = {
  components: [
    entry('rfid', 'rfid', true, {
      hardware: { de: 'PN532 am I2C', en: 'A PN532 on I2C' },
    }),
    entry('led', 'led', false),
    entry('button', 'button', false),
    entry('display', 'display', false),
    entry('media', 'media-downloader', false, { category: 'software', network: true }),
    METADATA,
  ],
  profiles: ['rfid'],
  channel: 'stable',
  busy: false,
};

describe('AddonsPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    get.mockResolvedValue(BOX);
    setSetting.mockResolvedValue(undefined);
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
    renderPanel();

    const apply = await screen.findByRole('button', { name: text('system.components_apply') });
    // Nothing changed yet, so there is nothing to apply.
    expect(apply).toBeDisabled();

    await user.click(screen.getByRole('checkbox', { name: text('system.component_led') }));
    expect(apply).toBeEnabled();
    // A flipped switch is a wish - the box is only touched on confirm.
    expect(put).not.toHaveBeenCalled();

    await user.click(apply);
    const dialog = await screen.findByRole('dialog');
    // The question says which addon is about to be switched on.
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

  it('re-reads the catalogue after a run', async () => {
    // What the box has is what the run just changed, and the states in the
    // table come from that same answer - a table left showing the wish would
    // claim the run did something it may not have done.
    const user = userEvent.setup();
    renderPanel();

    const apply = await screen.findByRole('button', { name: text('system.components_apply') });
    await user.click(screen.getByRole('checkbox', { name: text('system.component_led') }));
    await user.click(apply);
    const dialog = await screen.findByRole('dialog');
    await user.click(
      within(dialog).getByRole('button', { name: commonText('actions.confirm') }),
    );

    // Once when the panel opened, once after the run.
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
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
    renderPanel();

    await screen.findByRole('dialog');
    await waitFor(() => expect(getStatus).toHaveBeenCalled());
    // Nothing was started from here - it was already going.
    expect(put).not.toHaveBeenCalled();
  });

  it('describes an addon this box does not have', async () => {
    // The catalogue is what makes an addon findable without the
    // documentation: what it does, what it needs, and what would be installed.
    renderPanel();

    expect(await screen.findByText('Was media tut')).toBeInTheDocument();
    // Media import and online metadata: both talk to the internet, and both
    // say so where it can be read before switching them on.
    expect(screen.getAllByText(text('system.components_needs_network'))).toHaveLength(2);
    expect(
      screen.getByText(
        text('system.components_needs_hardware').replace('{{text}}', 'PN532 am I2C'),
      ),
    ).toBeInTheDocument();
  });

  it('sorts the addons by whether they need an accessory', async () => {
    // The one split that costs money and a screwdriver. Everything with
    // hardware behind it belongs in the first group.
    renderPanel();

    expect(await screen.findByText(text('addons.category_hardware'))).toBeInTheDocument();
    expect(screen.getByText(text('addons.category_software'))).toBeInTheDocument();
  });

  it('lists an addon this WebUI release does not know', async () => {
    // The name comes from the backend, so an addon added after this build
    // appears under its own name instead of a raw translation key - without a
    // WebUI release.
    get.mockResolvedValue({
      ...BOX,
      components: [
        ...BOX.components,
        entry('camera', 'camera', false, {
          name: { de: 'Kamera', en: 'Camera' },
          summary: { de: 'Nimmt Bilder auf', en: 'Takes pictures' },
        }),
      ],
      profiles: ['rfid'],
    });
    renderPanel();

    expect(await screen.findByRole('checkbox', { name: 'Kamera' })).toBeInTheDocument();
    expect(screen.getByText('Nimmt Bilder auf')).toBeInTheDocument();
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
    renderPanel();

    const apply = await screen.findByRole('button', { name: text('system.components_apply') });
    const led = screen.getByRole('checkbox', { name: text('system.component_led') });
    await user.click(led);
    await user.click(led);
    expect(apply).toBeDisabled();

    expect(getStatus).not.toHaveBeenCalled();
    expect(showSuccess).not.toHaveBeenCalled();
  });

  it('writes an addon that is a setting straight away', async () => {
    // No containers to recreate, so there is no run to collect it into -
    // waiting for "apply" would be a rule with no reason behind it.
    const user = userEvent.setup();
    renderPanel();

    await user.click(await screen.findByRole('checkbox', { name: 'Online-Metadaten' }));

    await waitFor(() =>
      expect(setSetting).toHaveBeenCalledWith('online_metadata_lookup_enabled', true),
    );
    // And nothing was collected: the compose addons are untouched.
    expect(
      screen.getByRole('button', { name: text('system.components_apply') }),
    ).toBeDisabled();
    expect(put).not.toHaveBeenCalled();
  });

  it('puts the switch back when the setting cannot be written', async () => {
    // A switch that claims something the box did not store is worse than an
    // error message.
    setSetting.mockRejectedValue(new Error('nope'));
    const user = userEvent.setup();
    renderPanel();

    const toggle = await screen.findByRole('checkbox', { name: 'Online-Metadaten' });
    await user.click(toggle);

    await waitFor(() => expect(showError).toHaveBeenCalled());
    await waitFor(() => expect(toggle).not.toBeChecked());
  });

  it('updates a single addon without touching the rest of the box', async () => {
    get.mockResolvedValue({
      ...BOX,
      components: [
        entry('rfid', 'rfid', true, { latest: '0.3.0', update_available: true }),
        ...BOX.components.slice(1),
      ],
    });
    const user = userEvent.setup();
    renderPanel();

    await user.click(
      await screen.findByRole('button', {
        name: text('addons.update_action').replace('{{name}}', text('system.component_rfid')),
      }),
    );
    const dialog = await screen.findByRole('dialog');
    await user.click(
      within(dialog).getByRole('button', { name: commonText('actions.confirm') }),
    );

    // One target, pinned to the published version - not "everything to latest".
    await waitFor(() => expect(startUpdate).toHaveBeenCalledWith({ rfid: '0.3.0' }));
  });

  it('links the gear button to the section the addon owns', async () => {
    // One value, one place to edit it (docs/services/webui/Settings-Structure.md):
    // the gear jumps to the settings page's own section instead of opening the
    // same form a second time.
    const user = userEvent.setup();
    renderPanel();

    await user.click(
      await screen.findByRole('button', {
        name: text('addons.settings_action').replace('{{name}}', text('system.component_rfid')),
      }),
    );

    expect(screen.getByTestId('location')).toHaveTextContent('/admin?section=rfid');
    // An addon that is not on the box has nothing to configure yet.
    expect(
      screen.queryByRole('button', {
        name: text('addons.settings_action').replace('{{name}}', text('system.component_led')),
      }),
    ).not.toBeInTheDocument();
  });

  it('has no settings link for an addon this WebUI cannot configure', async () => {
    // No `settings_section` means nothing to jump to - a gear button that led
    // nowhere would be worse than no button at all.
    get.mockResolvedValue({
      ...BOX,
      components: [
        entry('rfid', 'rfid', true, { settings_section: null }),
        ...BOX.components.slice(1),
      ],
    });
    renderPanel();

    await screen.findByRole('checkbox', { name: text('system.component_rfid') });
    expect(
      screen.queryByRole('button', {
        name: text('addons.settings_action').replace('{{name}}', text('system.component_rfid')),
      }),
    ).not.toBeInTheDocument();
  });
});
