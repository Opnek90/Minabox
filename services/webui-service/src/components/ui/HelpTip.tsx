import React, { useId, useState } from 'react';
import { Box, ClickAwayListener, Drawer, IconButton, Tooltip, Typography } from '@mui/material';
import HelpOutlineIcon from '@mui/icons-material/HelpOutline';
import { useTranslation } from 'react-i18next';
import { SAFE_AREA_BOTTOM } from '@/components/common/Navigation';
import { useLayout } from '@/hooks/useLayout';

interface HelpTipProps {
  /** The explanation itself - already translated, a whole sentence. */
  title: string;
  /**
   * Name of the setting being explained - already translated. Becomes the
   * heading of the sheet on the phone, where the explanation is torn out of
   * its place on the page and needs to say what it is about.
   */
  label?: string;
  /**
   * Layout tweaks from the call site (margins mostly). The icon size and
   * colour deliberately are not configurable - see below.
   */
  sx?: React.ComponentProps<typeof IconButton>['sx'];
}

/**
 * Question mark next to a label; the explanation appears on demand.
 *
 * Why this exists: the settings page used to carry the explanation as a
 * permanent caption under every field. Whole sentences ("Off by default,
 * because this sends the track title and artist to a third party") at dozens
 * of places turned the page into a wall of grey text you had to read past to
 * find the switch you came for. Background knowledge is worth having, but only
 * at the moment someone asks for it.
 *
 * Two presentations, because a tooltip is a desktop format. A dark bubble
 * capped at 320px is nearly the full width of a phone, hangs off a tiny icon
 * and may cover the very switch it explains - and three sentences read badly
 * in it. Below `sm` the explanation therefore arrives as a sheet from the
 * bottom edge: full reading width, a heading saying which setting this is
 * about, and it stays until dismissed. The same split `ResponsiveDialog`
 * makes for form dialogs.
 *
 * `disableTouchListener` is what keeps a scroll from opening the explanation.
 * MUI starts a timer at `touchstart` and never listens for `touchmove`: it
 * only cancels once the finger comes back up, so a swipe that begins on the
 * icon and lasts longer than the delay counts as a long press. The default
 * 700ms makes that a slow-scroll problem; it was a constant one while this
 * component passed `enterTouchDelay={0}`, which opened on contact. Our own
 * `onClick` does not have the ambiguity to begin with - a browser does not
 * fire `click` when the touch turns into a scroll. Giving up MUI's touch path
 * costs nothing else: it still marks the interaction as touch-driven and
 * swallows the emulated `mouseover` that follows a tap.
 *
 * Size and colour of the icon are fixed on purpose: it has to read as "there
 * is more to know here" and never as a control that does something. Every call
 * site tuning its own would bring back exactly the four-variants-side-by-side
 * mess that `SettingsBlock` was built to end.
 */
export const HelpTip: React.FC<HelpTipProps> = ({ title, label, sx }) => {
  const { t } = useTranslation('common');
  const { isMobile } = useLayout();
  const [open, setOpen] = useState(false);
  const headingId = useId();
  const textId = useId();

  const icon = (
    <IconButton
      type="button"
      aria-label={t('help.explain')}
      aria-haspopup={isMobile ? 'dialog' : undefined}
      onClick={(event) => {
        // Inside a `FormControlLabel` the icon sits within the `<label>` of
        // the switch. Per spec a nested button is not supposed to forward the
        // click to the control, and jsdom does honour that - this keeps a
        // browser that does not from flipping the very setting the question
        // mark explains.
        event.preventDefault();
        event.stopPropagation();
        setOpen((prev) => !prev);
      }}
      size="small"
      sx={{ color: 'text.secondary', p: 0.25, ...sx }}
    >
      <HelpOutlineIcon sx={{ fontSize: '1.05rem' }} />
    </IconButton>
  );

  if (isMobile) {
    return (
      <>
        {icon}
        <Drawer
          anchor="bottom"
          open={open}
          onClose={() => setOpen(false)}
          PaperProps={{
            // Rounded top edge so the sheet reads as laid over the page rather
            // than as a second page glued to the bottom.
            sx: { borderTopLeftRadius: 16, borderTopRightRadius: 16 },
            'aria-labelledby': label ? headingId : undefined,
            'aria-describedby': textId,
          }}
        >
          <Box sx={{ px: 2.5, pt: 1.5, pb: `calc(24px + ${SAFE_AREA_BOTTOM})` }}>
            {/* Grab bar - the one thing that says "this can be pushed away". */}
            <Box
              sx={{
                width: 36,
                height: 4,
                borderRadius: 2,
                bgcolor: 'divider',
                mx: 'auto',
                mb: 2,
              }}
            />
            {label && (
              <Typography id={headingId} variant="subtitle1" fontWeight={600} sx={{ mb: 0.75 }}>
                {label}
              </Typography>
            )}
            <Typography id={textId} variant="body2" color="text.secondary">
              {title}
            </Typography>
          </Box>
        </Drawer>
      </>
    );
  }

  return (
    <ClickAwayListener onClickAway={() => setOpen(false)}>
      <Tooltip
        title={title}
        open={open}
        onOpen={() => setOpen(true)}
        onClose={() => setOpen(false)}
        describeChild
        arrow
        disableTouchListener
        slotProps={{
          tooltip: { sx: { fontSize: '0.8125rem', lineHeight: 1.5, maxWidth: 320, p: 1.25 } },
        }}
      >
        {icon}
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
    <HelpTip title={help} label={text} />
  </Box>
);
