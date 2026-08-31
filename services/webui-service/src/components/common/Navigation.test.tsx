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

describe('Navigation - cards entry hangs off the RFID reader (#132)', () => {
  beforeEach(() => {
    rfidInstalled = true;
  });

  it('shows the RFID entry when the reader is installed', () => {
    renderNav(<Navigation />);
    expect(screen.getByText('navigation.rfid')).toBeInTheDocument();
  });

  it('hides the RFID entry when the reader is missing - in drawer and BottomNav', () => {
    rfidInstalled = false;
    const { rerender } = renderNav(<Navigation />);
    expect(screen.queryByText('navigation.rfid')).not.toBeInTheDocument();
    expect(screen.getByText('navigation.media')).toBeInTheDocument();

    rerender(<MemoryRouter initialEntries={['/media']}><MobileBottomNav /></MemoryRouter>);
    expect(screen.queryByText('navigation.rfid')).not.toBeInTheDocument();
  });
});
