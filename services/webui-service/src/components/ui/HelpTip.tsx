import React, { useState } from 'react';
import { Box, ClickAwayListener, IconButton, Tooltip } from '@mui/material';
import HelpOutlineIcon from '@mui/icons-material/HelpOutline';
import { useTranslation } from 'react-i18next';

interface HelpTipProps {
  /** The explanation itself - already translated, a whole sentence. */
  title: string;
  /**
   * Layout tweaks from the call site (margins mostly). The icon size and
   * colour deliberately are not configurable - see below.
   */
  sx?: React.ComponentProps<typeof IconButton>['sx'];
}

/**
 * Question mark next to a label; the explanation appears on hover or tap.
 *
 * Why this exists: the settings page used to carry the explanation as a
 * permanent caption under every field. Whole sentences ("Off by default,
 * because this sends the track title and artist to a third party") at dozens
 * of places turned the page into a wall of grey text you had to read past to
 * find the switch you came for. Background knowledge is worth having, but only
 * at the moment someone asks for it.
 *
 * Two things this component does that a bare `<Tooltip>` does not:
 *
 * - It opens on click as well as on hover. The box is operated from a phone
 *   and a tablet at least as often as from a desktop, and there is no hover
 *   there - MUI's touch fallback is a long press, which nobody discovers. The
 *   controlled `open` plus `ClickAwayListener` makes a tap work everywhere,
 *   including with a mouse.
 * - It stays a real `<button>` with an `aria-label`, so the explanation is
 *   reachable by keyboard and gets announced. `describeChild` hands the
 *   tooltip text to the screen reader as the description rather than as the
 *   name, which is what the caption did before.
 *
 * Size and colour are fixed on purpose: the icon has to read as "there is more
 * to know here" and never as a control that does something. Every call site
 * tuning its own would bring back exactly the four-variants-side-by-side mess
 * that `SettingsBlock` was built to end.
 */
export const HelpTip: React.FC<HelpTipProps> = ({ title, sx }) => {
  const { t } = useTranslation('common');
  const [open, setOpen] = useState(false);

  return (
    <ClickAwayListener onClickAway={() => setOpen(false)}>
      <Tooltip
        title={title}
        open={open}
        onOpen={() => setOpen(true)}
        onClose={() => setOpen(false)}
        describeChild
        arrow
        // The touch delays only apply to the long press, which we keep as a
        // second route in; the tap below is instant either way.
        enterTouchDelay={0}
        leaveTouchDelay={8000}
        slotProps={{
          tooltip: { sx: { fontSize: '0.8125rem', lineHeight: 1.5, maxWidth: 320, p: 1.25 } },
        }}
      >
        <IconButton
          type="button"
          aria-label={t('help.explain')}
          onClick={(event) => {
            // Inside a `FormControlLabel` the icon sits within the `<label>`
            // of the switch. Per spec a nested button is not supposed to
            // forward the click to the control, and jsdom does honour that -
            // this keeps a browser that does not from flipping the very
            // setting the question mark explains.
            event.preventDefault();
            event.stopPropagation();
            setOpen((prev) => !prev);
          }}
          size="small"
          sx={{ color: 'text.secondary', p: 0.25, ...sx }}
        >
          <HelpOutlineIcon sx={{ fontSize: '1.05rem' }} />
        </IconButton>
      </Tooltip>
    </ClickAwayListener>
  );
};

interface HelpLabelProps {
  text: string;
  /** The explanation for the question mark - already translated. */
  help: string;
}

/**
 * A label with its question mark right behind it, for the places where the
 * label is not plain text but a node: `FormControlLabel` for switches, and the
 * headings of `SettingsBlock`/`SettingsSection`.
 *
 * `component="span"` and `display="inline-flex"` are what keeps the switch row
 * from breaking: `FormControlLabel` puts its label inside a `<label>`, so a
 * `<div>` in there is invalid markup and lands the icon on its own line.
 */
export const HelpLabel: React.FC<HelpLabelProps> = ({ text, help }) => (
  <Box component="span" sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.5 }}>
    {text}
    <HelpTip title={help} />
  </Box>
);
