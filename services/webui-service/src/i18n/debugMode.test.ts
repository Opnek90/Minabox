import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// The i18n instance is replaced with a minimal double, so the test does not
// trigger i18next.init() with the HTTP backend.
const fakeI18n = {
  language: 'de',
  options: {} as Record<string, unknown>,
  changeLanguage: vi.fn(),
};

vi.mock('./index', () => ({ default: fakeI18n }));

const getGeneral = vi.fn();
vi.mock('@/api/config', () => ({ configApi: { getGeneral: () => getGeneral() } }));

async function freshImport() {
  vi.resetModules();
  return import('./debugMode');
}

beforeEach(() => {
  vi.clearAllMocks();
  fakeI18n.language = 'de';
  fakeI18n.options = {};
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('applyI18nDebugMode', () => {
  it('turns off the fallback at log_level "debug" and reports missing keys', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    vi.spyOn(console, 'info').mockImplementation(() => {});
    const { applyI18nDebugMode } = await freshImport();

    applyI18nDebugMode('debug');

    expect(fakeI18n.options.fallbackLng).toBe(false);
    expect(fakeI18n.options.saveMissing).toBe(true);
    expect(fakeI18n.changeLanguage).toHaveBeenCalledWith('de');

    const handler = fakeI18n.options.missingKeyHandler as (
      lngs: readonly string[],
      ns: string,
      key: string,
    ) => void;
    handler(['de'], 'media', 'media.tracks.play');
    expect(warn).toHaveBeenCalledWith(expect.stringContaining('[media] media.tracks.play'));
  });

  it('laesst bei jedem anderen Log-Level alles unveraendert', async () => {
    const { applyI18nDebugMode } = await freshImport();

    applyI18nDebugMode('info');

    expect(fakeI18n.options.fallbackLng).toBeUndefined();
    expect(fakeI18n.options.saveMissing).toBeUndefined();
    expect(fakeI18n.changeLanguage).not.toHaveBeenCalled();
  });

  it('wirkt nur einmal, auch bei mehrfachem Aufruf', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    vi.spyOn(console, 'info').mockImplementation(() => {});
    const { applyI18nDebugMode } = await freshImport();

    applyI18nDebugMode('debug');
    applyI18nDebugMode('debug');

    expect(fakeI18n.changeLanguage).toHaveBeenCalledTimes(1);
  });
});

describe('activateI18nDebugModeFromConfig', () => {
  it('enables debug mode when the server reports "debug"', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    vi.spyOn(console, 'info').mockImplementation(() => {});
    getGeneral.mockResolvedValue({ log_level: 'debug' });
    const { activateI18nDebugModeFromConfig } = await freshImport();

    await activateI18nDebugModeFromConfig();

    expect(fakeI18n.options.fallbackLng).toBe(false);
  });

  it('swallows a fetch error and leaves the fallback in place', async () => {
    getGeneral.mockRejectedValue(new Error('offline'));
    const { activateI18nDebugModeFromConfig } = await freshImport();

    await expect(activateI18nDebugModeFromConfig()).resolves.toBeUndefined();
    expect(fakeI18n.options.fallbackLng).toBeUndefined();
  });
});
