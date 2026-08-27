import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { MobileBottomNav, Navigation } from './Navigation';

let rfidInstalled = true;

vi.mock('@/contexts/CapabilitiesContext', () => ({
  useFeatureInstalled: (key: string) => (key === 'rfid' ? rfidInstalled : true),
}));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'de' } }),
}));

const renderNav = (node: React.ReactNode) =>
  render(<MemoryRouter initialEntries={['/media']}>{node}</MemoryRouter>);

describe('Navigation – Karten-Eintrag haengt am RFID-Leser (#132)', () => {
  beforeEach(() => {
    rfidInstalled = true;
  });

  it('zeigt den RFID-Eintrag, wenn der Leser installiert ist', () => {
    renderNav(<Navigation />);
    expect(screen.getByText('navigation.rfid')).toBeInTheDocument();
  });

  it('blendet den RFID-Eintrag aus, wenn der Leser fehlt - in Drawer und BottomNav', () => {
    rfidInstalled = false;
    const { rerender } = renderNav(<Navigation />);
    expect(screen.queryByText('navigation.rfid')).not.toBeInTheDocument();
    expect(screen.getByText('navigation.media')).toBeInTheDocument();

    rerender(<MemoryRouter initialEntries={['/media']}><MobileBottomNav /></MemoryRouter>);
    expect(screen.queryByText('navigation.rfid')).not.toBeInTheDocument();
  });
});
