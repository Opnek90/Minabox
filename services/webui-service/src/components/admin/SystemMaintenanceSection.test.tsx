import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import deAdmin from '../../../public/locales/de/admin.json';
import deCommon from '../../../public/locales/de/common.json';
import { SystemMaintenanceSection } from './SystemMaintenanceSection';

/**
 * Regressionstest zu #137: Nach Abschluss eines Updates fragte die
 * 2-Sekunden-Schleife den Status endlos weiter ab und schob bei jedem
 * Durchlauf erneut die Erfolgsmeldung in die Snackbar. Der Endzustand darf
 * nur einmal gemeldet werden, danach muss die Abfrage ruhen.
 */

const showSuccess = vi.fn();
const showError = vi.fn();

const getUpdateCheck = vi.fn();
const updateMinabox = vi.fn();
const getUpdateStatus = vi.fn();
const getUpdateOsLog = vi.fn();
const getGeneral = vi.fn();

vi.mock('@/api/system', () => ({
  systemApi: {
    getUpdateCheck: (...a: unknown[]) => getUpdateCheck(...a),
    updateMinabox: (...a: unknown[]) => updateMinabox(...a),
    getUpdateStatus: (...a: unknown[]) => getUpdateStatus(...a),
    getUpdateOsLog: (...a: unknown[]) => getUpdateOsLog(...a),
  },
}));

vi.mock('@/api/config', () => ({
  configApi: {
    getGeneral: (...a: unknown[]) => getGeneral(...a),
    updateGeneral: vi.fn().mockResolvedValue({}),
  },
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
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) => {
      const bundle = options?.ns === 'common' ? deCommon : deAdmin;
      return lookup(bundle, key) ?? key;
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

const TERMINAL_STATUS = {
  running: false,
  step: 4,
  step_count: 4,
  step_key: 'verify',
  steps: [],
  exit_code: 0,
  log: 'done',
};

describe('SystemMaintenanceSection – Update-Abschluss (#137)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getGeneral.mockResolvedValue({ auto_update_check_enabled: false });
    getUpdateOsLog.mockResolvedValue({ running: false, log: '' });
    getUpdateCheck.mockResolvedValue({
      checked_at: '2026-08-27T00:00:00Z',
      from_cache: false,
      update_available: true,
      error: null,
      services: [
        {
          service: 'webui',
          installed: '0.1.0',
          latest: '0.2.0',
          update_available: true,
          managed: true,
          releases: [],
        },
      ],
    });
    updateMinabox.mockResolvedValue({ ok: true });
    // Die Schleife sieht sofort den Endzustand.
    getUpdateStatus.mockResolvedValue(TERMINAL_STATUS);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('meldet den Erfolg genau einmal und stellt die Status-Abfrage danach ein', async () => {
    const user = userEvent.setup();
    render(<SystemMaintenanceSection />);

    const openDialog = await screen.findByRole('button', { name: text('system.update_minabox') });
    await user.click(openDialog);

    const confirm = await screen.findByRole('button', { name: commonText('actions.confirm') });
    await user.click(confirm);

    await waitFor(() => expect(showSuccess).toHaveBeenCalledTimes(1));
    expect(showSuccess).toHaveBeenCalledWith(text('system.update_success'));

    // Nach dem gemeldeten Endzustand darf nicht weiter gepollt werden: der
    // Zaehler bleibt ueber mehrere Intervalle hinweg stehen.
    const callsAfterSettle = getUpdateStatus.mock.calls.length;
    await new Promise((r) => setTimeout(r, 5000));
    expect(getUpdateStatus.mock.calls.length).toBe(callsAfterSettle);
    expect(showSuccess).toHaveBeenCalledTimes(1);
  }, 15000);
});
