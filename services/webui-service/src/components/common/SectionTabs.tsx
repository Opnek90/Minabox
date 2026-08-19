import React, { useRef } from 'react';
import { Box, ButtonBase, Tab, Tabs } from '@mui/material';
import { useLayout } from '@/hooks/useLayout';

export interface SectionTabItem {
  /** Vollstaendiger Bereichsname – Desktop-Tab, Vorlesename, aktive Pille. */
  label: string;
  /** Symbol des Bereichs. Traegt auf dem Telefon die inaktiven Bereiche allein. */
  icon: React.ReactNode;
  /** Umfang des Bereichs; erscheint als kleine Marke am Symbol. */
  count?: number;
}

interface SectionTabsProps {
  value: number;
  onChange: (value: number) => void;
  /** Bereiche in Reihenfolge; der Index ist der Tab-Wert. */
  sections: SectionTabItem[];
  /** Screenreader-Bezeichnung der Bereichsauswahl. */
  ariaLabel?: string;
}

/**
 * Bereichsumschaltung einer Seite – Tabs auf dem Desktop, Symbolleiste auf dem
 * Telefon.
 *
 * Hintergrund: MUI gibt jedem `Tab` `minWidth: 90px`. Fuenf Bereiche brauchen
 * damit mindestens 450px; auf einem 390px-Geraet bleiben nach dem Seiten-
 * Padding 366px. Die Leiste lief also zwangslaeufig ueber.
 *
 * Das Platzproblem entsteht aber nur, weil *jeder* Bereich Text traegt.
 * Unterhalb `sm` bekommt deshalb nur der aktive Bereich seinen Namen und
 * waechst zur Pille; die uebrigen stehen als Symbol daneben und sind einen
 * Tipp entfernt. Der frueher hier stehende Zaehler ("2/5") entfaellt: Er
 * zaehlte eine Liste, die man nicht sah.
 *
 * Breitenverteilung: Die aktive Pille bekommt ihre *Inhaltsbreite*
 * (`flex: 0 1 auto`), die Symbole teilen sich den Rest (`flex: 1 1 0`). Damit
 * kann der Name nicht abgeschnitten werden, solange die Zeile ueberhaupt
 * reicht – die frueher uebliche Rechnung "Restbreite minus Symbole" hat genau
 * das getan. Erst wenn selbst 40px je Symbol nicht mehr passen, kuerzt die
 * Pille mit Auslassungspunkten.
 */
const ICON_SIZE = 40;
const LABEL_TRANSITION = 'max-width 250ms cubic-bezier(0.2, 0.8, 0.3, 1), margin-left 250ms cubic-bezier(0.2, 0.8, 0.3, 1), opacity 160ms ease';

export const SectionTabs: React.FC<SectionTabsProps> = ({
  value,
  onChange,
  sections,
  ariaLabel,
}) => {
  const isMobile = useLayout().isMobile;
  const barRef = useRef<HTMLDivElement>(null);

  if (!isMobile) {
    return (
      <Tabs
        value={value}
        onChange={(_, v: number) => onChange(v)}
        variant="scrollable"
        scrollButtons="auto"
        aria-label={ariaLabel}
        sx={{ borderBottom: 1, borderColor: 'divider' }}
      >
        {sections.map((section) => (
          <Tab key={section.label} label={section.label} />
        ))}
      </Tabs>
    );
  }

  /** Pfeiltasten wandern durch die Leiste, wie es ARIA fuer `tablist` erwartet. */
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
        gap: 0.5,
        px: 0.5,
        py: 1,
        borderBottom: 1,
        borderColor: 'divider',
      }}
    >
      {sections.map((section, index) => {
        const selected = index === value;
        return (
          <ButtonBase
            key={section.label}
            role="tab"
            aria-selected={selected}
            tabIndex={selected ? 0 : -1}
            // Inaktiv steht nur das Symbol da – der Name muss trotzdem vorgelesen werden.
            aria-label={
              section.count === undefined
                ? section.label
                : `${section.label}, ${section.count}`
            }
            onClick={() => onChange(index)}
            sx={{
              flex: selected ? '0 1 auto' : '1 1 0',
              minWidth: ICON_SIZE,
              height: ICON_SIZE,
              px: selected ? 1.25 : 0,
              borderRadius: ICON_SIZE / 2,
              justifyContent: 'center',
              // Kein `overflow: hidden` auf der Schaltflaeche: Der Name kuerzt sich
              // selbst, die Mengenmarke wuerde hier aber angeschnitten – bei 320px
              // bleiben je Symbol nur ~41px, und "128" ragt darueber hinaus.
              color: selected ? 'primary.contrastText' : 'text.secondary',
              bgcolor: selected ? 'primary.main' : 'transparent',
              transition: 'background-color 200ms ease, color 200ms ease',
              '& > .section-tab-icon svg': { fontSize: 20, display: 'block' },
            }}
          >
            <Box component="span" className="section-tab-icon" sx={{ position: 'relative', flexShrink: 0 }}>
              {section.icon}
              {/* Bei leerem Bereich keine Null-Marke: fuenf Nullen sind Laerm, keine Information. */}
              {!selected && !!section.count && (
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
                  {section.count > 99 ? '99+' : section.count}
                </Box>
              )}
            </Box>
            <Box
              component="span"
              sx={{
                // Der Name faehrt auf, statt hart einzublenden: Die Pille waechst
                // sichtbar aus dem Symbol heraus, das man gerade getippt hat.
                maxWidth: selected ? '14ch' : 0,
                ml: selected ? 0.75 : 0,
                opacity: selected ? 1 : 0,
                minWidth: 0,
                overflow: 'hidden',
                whiteSpace: 'nowrap',
                textOverflow: 'ellipsis',
                fontSize: 13.5,
                // 500 statt 600: Roboto liegt nur in 300/400/500/700 vor – 600
                // wuerde der Browser auf 700 hochziehen und die Pille breiter machen.
                fontWeight: 500,
                lineHeight: 1.2,
                transition: LABEL_TRANSITION,
              }}
            >
              {section.label}
            </Box>
          </ButtonBase>
        );
      })}
    </Box>
  );
};
