import React, { useRef } from 'react';
import { Box, ButtonBase } from '@mui/material';
import { useLayout } from '@/hooks/useLayout';

export interface SectionTabItem {
  /** Full area name - the pill, the read-out name. */
  label: string;
  /** Icon of the area. Carries the inactive areas on its own on the phone. */
  icon: React.ReactNode;
  /** Size of the area; a number in the pill, a badge on the icon on the phone. */
  count?: number;
}

interface SectionTabsProps {
  value: number;
  onChange: (value: number) => void;
  /** Areas in order; the index is the tab value. */
  sections: SectionTabItem[];
  /** Screen-reader label of the area selector. */
  ariaLabel?: string;
}

/**
 * Area switcher for a page - a pill bar at all levels.
 *
 * Background: MUI gives every `Tab` `minWidth: 90px`. Five areas therefore need
 * at least 450px; on a 390px device 366px remain after the page padding. So the
 * tab bar inevitably overflowed.
 *
 * But the space problem only arises because *every* area carries text. On the
 * phone, therefore, only the active area gets its name and grows into a pill;
 * the others stand next to it as an icon and are one tap away. From tablet up
 * there is enough room, where all pills carry an icon, name and count - the
 * same component, the same picture, just more labelling.
 *
 * Width distribution on the phone: the active pill gets its *content width*
 * (`flex: 0 1 auto`), the icons share the rest (`flex: 1 1 0`). This means the
 * name cannot be cut off as long as the row is wide enough at all - the obvious
 * calculation "remaining width minus icons" did exactly that. Only when even
 * 36px per icon no longer fit does the pill truncate with an ellipsis.
 */
const PILL_HEIGHT = 40;
const LABEL_TRANSITION =
  'max-width 250ms cubic-bezier(0.2, 0.8, 0.3, 1), margin-left 250ms cubic-bezier(0.2, 0.8, 0.3, 1), opacity 160ms ease';

/**
 * The header is fixed, the bar sticks exactly below it. The values are MUI's
 * toolbar heights (`theme.mixins.toolbar`): 56px on the phone, 48px in
 * landscape, 64px from `sm`. If they differ, the bar slides under the header or
 * leaves a gap.
 */
const STICKY_TOP = {
  top: 56,
  '@media (min-width:0px) and (orientation: landscape)': { top: 48 },
  '@media (min-width:600px)': { top: 64 },
};

export const SectionTabs: React.FC<SectionTabsProps> = ({
  value,
  onChange,
  sections,
  ariaLabel,
}) => {
  // Only two things depend on the level: whether inactive pills show their
  // name and whether the count is a number in the pill or a badge on the icon.
  const compact = useLayout().isMobile;
  const barRef = useRef<HTMLDivElement>(null);

  /** Arrow keys move through the bar, as ARIA expects for `tablist`. */
  const handleKeyDown = (event: React.KeyboardEvent) => {
    const delta = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0;
    if (!delta) return;
    event.preventDefault();
    const next = (value + delta + sections.length) % sections.length;
    onChange(next);
    const buttons = barRef.current?.querySelectorAll<HTMLElement>('[role="tab"]');
    buttons?.[next]?.focus();
  };

  return (
    <Box
      ref={barRef}
      role="tablist"
      aria-label={ariaLabel}
      onKeyDown={handleKeyDown}
      sx={{
        display: 'flex',
        alignItems: 'center',
        // From tablet up the pills may wrap - two lines are acceptable there,
        // whereas a horizontal scrollbar hides areas.
        flexWrap: compact ? 'nowrap' : 'wrap',
        gap: compact ? 0.5 : 1,
        rowGap: 1,
        px: compact ? 0.5 : 0,
        py: 1,
        borderBottom: 1,
        borderColor: 'divider',
        position: 'sticky',
        ...STICKY_TOP,
        // Without an explicit ground, the scrolling content shows through the bar.
        bgcolor: 'background.default',
        zIndex: (theme) => theme.zIndex.appBar - 1,
        // Tighter spacing where it really gets tight: at 320px, 288px remain
        // after page padding, of which four icons plus gaps eat 176px.
        '@media (max-width: 359.95px)': { gap: 0.375 },
      }}
    >
      {sections.map((section, index) => {
        const selected = index === value;
        const showCount = section.count !== undefined && section.count > 0;
        return (
          <ButtonBase
            key={section.label}
            role="tab"
            aria-selected={selected}
            tabIndex={selected ? 0 : -1}
            // On the phone, only the icon stands there when inactive - the
            // name still has to be read out.
            aria-label={
              section.count === undefined
                ? section.label
                : `${section.label}, ${section.count}`
            }
            onClick={() => onChange(index)}
            sx={{
              flex: compact ? (selected ? '0 1 auto' : '1 1 0') : '0 0 auto',
              minWidth: compact ? PILL_HEIGHT : 0,
              height: PILL_HEIGHT,
              px: compact ? (selected ? 1.25 : 0) : 1.75,
              borderRadius: PILL_HEIGHT / 2,
              justifyContent: 'center',
              // No `overflow: hidden` on the button: the name truncates
              // itself, but the count badge would be clipped here - at 320px
              // only ~41px per icon remain, and "128" sticks out over it.
              color: selected ? 'primary.contrastText' : 'text.secondary',
              // primary.dark instead of .main: white text needs 4.5:1 (WCAG
              // AA, normal text). .main only reaches ~3.8:1 for the orange
              // preset and reads correspondingly pale; .dark clears it for all
              // presets. The same calculation is in Navigation.tsx for the
              // selected navigation entry.
              bgcolor: selected ? 'primary.dark' : 'transparent',
              '&:hover': { bgcolor: selected ? 'primary.dark' : 'action.hover' },
              transition: 'background-color 200ms ease, color 200ms ease',
              '& > .section-tab-icon svg': { fontSize: 20, display: 'block' },
              '@media (max-width: 359.95px)': { minWidth: compact ? 36 : 0 },
            }}
          >
            <Box
              component="span"
              className="section-tab-icon"
              sx={{ position: 'relative', flexShrink: 0 }}
            >
              {section.icon}
              {/* No zero badge for an empty area: five zeroes are noise, not information. */}
              {compact && !selected && showCount && (
                <Box
                  component="span"
                  sx={{
                    position: 'absolute',
                    top: -6,
                    left: 11,
                    minWidth: 16,
                    px: '3px',
                    borderRadius: 1,
                    border: 1,
                    borderColor: 'divider',
                    bgcolor: 'background.paper',
                    color: 'text.secondary',
                    fontSize: 9,
                    lineHeight: '14px',
                    fontVariantNumeric: 'tabular-nums',
                    textAlign: 'center',
                  }}
                >
                  {section.count! > 99 ? '99+' : section.count}
                </Box>
              )}
            </Box>

            <Box
              component="span"
              sx={{
                // On the phone the name slides in instead of appearing
                // abruptly: the pill visibly grows out of the icon that was
                // just tapped. From tablet up it is permanently there anyway.
                maxWidth: compact ? (selected ? '14ch' : 0) : 'none',
                ml: compact && !selected ? 0 : 0.75,
                opacity: compact && !selected ? 0 : 1,
                minWidth: 0,
                overflow: 'hidden',
                whiteSpace: 'nowrap',
                textOverflow: 'ellipsis',
                // Size from the theme instead of a rem literal: this way the
                // pill follows the font-size toggle and lands on whole pixels
                // (14px or 16px) instead of snapping to 15.75px at an 18px root.
                fontSize: (theme) => theme.typography.body2.fontSize,
                // 700 instead of 600: Roboto only comes in 300/400/500/700,
                // the browser would round 600 up to 700 anyway.
                fontWeight: 700,
                lineHeight: 1.2,
                transition: compact ? LABEL_TRANSITION : undefined,
              }}
            >
              {section.label}
            </Box>

            {/* From tablet up there is room for the count as a number - that replaces the badge. */}
            {!compact && showCount && (
              <Box
                component="span"
                sx={{
                  ml: 0.75,
                  fontSize: (theme) => theme.typography.caption.fontSize,
                  fontWeight: 500,
                  lineHeight: 1.2,
                  opacity: 0.7,
                  fontVariantNumeric: 'tabular-nums',
                }}
              >
                {section.count}
              </Box>
            )}
          </ButtonBase>
        );
      })}
    </Box>
  );
};
