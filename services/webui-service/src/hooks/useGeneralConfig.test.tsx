import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

import { useGeneralConfigField, useGeneralConfigFields } from './useGeneralConfig';

const getGeneral = vi.fn();
const updateGeneral = vi.fn();

vi.mock('@/api/config', () => ({
  configApi: {
    getGeneral: () => getGeneral(),
    updateGeneral: (patch: unknown) => updateGeneral(patch),
  },
}));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'de', exists: () => false } }),
}));
vi.mock('@/contexts/ToastContext', () => ({ useToast: () => ({ showSuccess: vi.fn() }) }));

const SERVER = {
  sleep_timer_minutes: 45,
  max_upload_size_mb: 250,
  playlist_shuffle: false,
};

const Single = () => {
  const { value } = useGeneralConfigField('sleep_timer_minutes', 30);
  return <span data-testid="single">{value === null ? 'loading' : String(value)}</span>;
};

const Other = () => {
  const { value } = useGeneralConfigField('max_upload_size_mb', 100);
  return <span data-testid="other">{value === null ? 'loading' : String(value)}</span>;
};

const Multi = () => {
  const { values } = useGeneralConfigFields({ playlist_shuffle: true, sleep_timer_minutes: 30 });
  return <span data-testid="multi">{values ? `${values.playlist_shuffle}/${values.sleep_timer_minutes}` : 'loading'}</span>;
};

describe('useGeneralConfig', () => {
  beforeEach(() => {
    getGeneral.mockReset();
    updateGeneral.mockReset();
  });

  it('nimmt den Serverwert und faellt sonst auf den Standard zurueck', async () => {
    getGeneral.mockResolvedValue({ sleep_timer_minutes: 45 });
    render(<Multi />);
    // sleep_timer_minutes kommt vom Server, playlist_shuffle fehlt dort
    await waitFor(() => expect(screen.getByTestId('multi')).toHaveTextContent('true/45'));
  });

  it('bündelt gleichzeitig startende Formulare zu einer Anfrage', async () => {
    let resolve: (v: unknown) => void = () => {};
    getGeneral.mockImplementation(() => new Promise((r) => { resolve = r; }));

    // Drei Formulare derselben Einstellungsgruppe, gemeinsam eingehaengt
    render(<><Single /><Other /><Multi /></>);
    expect(getGeneral).toHaveBeenCalledTimes(1);

    resolve(SERVER);
    await waitFor(() => expect(screen.getByTestId('single')).toHaveTextContent('45'));
    expect(screen.getByTestId('other')).toHaveTextContent('250');
    expect(getGeneral).toHaveBeenCalledTimes(1);
  });

  it('fragt nach dem Abschluss wieder frisch ab, cacht also nicht', async () => {
    getGeneral.mockResolvedValue(SERVER);
    const first = render(<Single />);
    await waitFor(() => expect(screen.getByTestId('single')).toHaveTextContent('45'));
    first.unmount();

    render(<Single />);
    await waitFor(() => expect(getGeneral).toHaveBeenCalledTimes(2));
  });

  it('meldet einen Ladefehler, statt still leer zu bleiben', async () => {
    getGeneral.mockRejectedValue(new Error('offline'));
    const Probe = () => {
      const { value, error } = useGeneralConfigField('sleep_timer_minutes', 30);
      return <span data-testid="probe">{error ?? (value === null ? 'loading' : String(value))}</span>;
    };
    render(<Probe />);
    await waitFor(() => expect(screen.getByTestId('probe')).toHaveTextContent('load_error'));
  });
});
