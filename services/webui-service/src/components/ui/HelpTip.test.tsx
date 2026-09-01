import { render, screen, waitForElementToBeRemoved } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { FormControlLabel, Switch } from '@mui/material';
import { describe, expect, it, vi } from 'vitest';

import { HelpLabel, HelpTip } from './HelpTip';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => (key === 'help.explain' ? 'Erklaerung anzeigen' : key),
    i18n: { language: 'de', changeLanguage: vi.fn() },
  }),
}));

const questionMark = () => screen.getByRole('button', { name: 'Erklaerung anzeigen' });

describe('HelpTip', () => {
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
