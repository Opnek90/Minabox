import { act, fireEvent, render, screen, waitForElementToBeRemoved } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { FormControlLabel, Switch } from '@mui/material';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { HelpLabel, HelpTip } from './HelpTip';

// The layout tier decides the presentation, so the tests set it directly
// instead of going through matchMedia.
const isMobile = vi.hoisted(() => ({ value: false }));
vi.mock('@/hooks/useLayout', () => ({
  useLayout: () => ({
    tier: isMobile.value ? 'mobile' : 'desktop',
    isMobile: isMobile.value,
    isTablet: false,
    isDesktop: !isMobile.value,
    isCompact: isMobile.value,
    hasRoomForInlineControls: !isMobile.value,
    pagePadding: 2,
  }),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => (key === 'help.explain' ? 'Erklaerung anzeigen' : key),
    i18n: { language: 'de', changeLanguage: vi.fn() },
  }),
}));

const questionMark = () => screen.getByRole('button', { name: 'Erklaerung anzeigen' });

describe('HelpTip', () => {
  beforeEach(() => {
    isMobile.value = false;
  });

  // The whole point of the component: on a phone there is no hover, so the
  // explanation has to be reachable by tapping.
  it('opens the explanation on click and closes it on the next one', async () => {
    const user = userEvent.setup();
    render(<HelpTip title="Wird an einen Dritten uebermittelt." />);

    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();

    await user.click(questionMark());
    expect(await screen.findByRole('tooltip')).toHaveTextContent(
      'Wird an einen Dritten uebermittelt.',
    );

    await user.click(questionMark());
    // The popper hangs around for the fade-out.
    await waitForElementToBeRemoved(() => screen.queryByRole('tooltip'));
  });

  // For a screen reader the explanation is the *description* of the question
  // mark, not its name - so it is announced after "Show explanation, button"
  // instead of replacing it.
  it('hands the explanation to the screen reader as a description', async () => {
    const user = userEvent.setup();
    render(<HelpTip title="Standardmaessig aus." />);

    await user.click(questionMark());
    expect(questionMark()).toHaveAccessibleDescription('Standardmaessig aus.');
  });

  // The reported fault: MUI opens on a timer started at `touchstart` and never
  // listens for `touchmove`, so a swipe beginning on the icon counted as a
  // long press. A tablet still takes this branch, so the guard belongs here.
  it('stays shut when a touch turns into a scroll', () => {
    vi.useFakeTimers();
    try {
      render(<HelpTip title="Standardmaessig aus." />);

      const icon = questionMark();
      fireEvent.touchStart(icon, { touches: [{ clientX: 10, clientY: 40 }] });
      fireEvent.touchMove(icon, { touches: [{ clientX: 10, clientY: 220 }] });
      // The finger is still down while the page moves - lifting it first would
      // clear MUI's timer and hide the very thing under test.
      act(() => vi.advanceTimersByTime(2000));

      expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();

      // And nothing arrives late either: a browser does not fire `click` when
      // the touch resolved as a scroll.
      fireEvent.touchEnd(icon);
      act(() => vi.advanceTimersByTime(2000));
      expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  // The icon sits inside the switch's <label>, where a click can reach the
  // control as well - which would flip the setting the icon explains.
  it('does not toggle the switch it explains', async () => {
    const user = userEvent.setup();
    render(
      <FormControlLabel
        control={<Switch />}
        label={<HelpLabel text="Online-Suche" help="Standardmaessig aus." />}
      />,
    );

    const toggle = screen.getByRole('checkbox', { name: 'Online-Suche' });
    expect(toggle).not.toBeChecked();

    await user.click(questionMark());
    expect(toggle).not.toBeChecked();
  });
});

describe('HelpTip on a phone', () => {
  beforeEach(() => {
    isMobile.value = true;
  });

  // A tooltip is a desktop format: 320px of dark bubble on a 360px screen,
  // hanging off the very control it explains.
  it('shows the explanation in a sheet, with the setting it belongs to', async () => {
    const user = userEvent.setup();
    render(<HelpTip title="Standardmaessig aus." label="Online-Suche" />);

    expect(screen.queryByRole('presentation')).not.toBeInTheDocument();

    await user.click(questionMark());
    const sheet = await screen.findByRole('presentation');
    expect(sheet).toHaveTextContent('Online-Suche');
    expect(sheet).toHaveTextContent('Standardmaessig aus.');
    // Torn out of its place on the page, the text has to say what it is about.
    expect(screen.getByRole('heading', { name: 'Online-Suche' })).toBeInTheDocument();
  });

  it('does not put a tooltip on the page as well', async () => {
    const user = userEvent.setup();
    render(<HelpTip title="Standardmaessig aus." label="Online-Suche" />);

    await user.click(questionMark());
    await screen.findByRole('presentation');
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
  });
});
