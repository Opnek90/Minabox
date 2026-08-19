import React, { useRef } from 'react';
import { Box, ButtonBase } from '@mui/material';
import { useLayout } from '@/hooks/useLayout';

export interface SectionTabItem {
  /** Vollstaendiger Bereichsname – Pille, Vorlesename. */
  label: string;
  /** Symbol des Bereichs. Traegt auf dem Telefon die inaktiven Bereiche allein. */
  icon: React.ReactNode;
  /** Umfang des Bereichs; Zahl in der Pille, am Telefon Marke am Symbol. */
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
 * Bereichsumschaltung einer Seite – eine Pillenleiste auf allen Stufen.
 *
 * Hintergrund: MUI gibt jedem `Tab` `minWidth: 90px`. Fuenf Bereiche brauchen
 * damit mindestens 450px; auf einem 390px-Geraet bleiben nach dem Seiten-
 * Padding 366px. Die Tab-Leiste lief also zwangslaeufig ueber.
 *
 * Das Platzproblem entsteht aber nur, weil *jeder* Bereich Text traegt. Auf dem
 * Telefon bekommt deshalb nur der aktive Bereich seinen Namen und waechst zur
 * Pille; die uebrigen stehen als Symbol daneben und sind einen Tipp entfernt.
 * Ab Tablet ist Platz genug, dort tragen alle Pillen Symbol, Namen und Menge –
 * dasselbe Bauteil, dasselbe Bild, nur mehr Beschriftung.
 *
 * Breitenverteilung am Telefon: Die aktive Pille bekommt ihre *Inhaltsbreite*
 * (`flex: 0 1 auto`), die Symbole teilen sich den Rest (`flex: 1 1 0`). Damit
 * kann der Name nicht abgeschnitten werden, solange die Zeile ueberhaupt
 * reicht – die naheliegende Rechnung "Restbreite minus Symbole" hat genau das
 * getan. Erst wenn selbst 36px je Symbol nicht mehr passen, kuerzt die Pille
 * mit Auslassungspunkten.
 */
const PILL_HEIGHT = 40;
const LABEL_TRANSITION =
  'max-width 250ms cubic-bezier(0.2, 0.8, 0.3, 1), margin-left 250ms cubic-bezier(0.2, 0.8, 0.3, 1), opacity 160ms ease';

/**
 * Die Kopfzeile ist fixiert, die Leiste klebt genau darunter. Die Werte sind
 * MUIs Toolbar-Hoehen (`theme.mixins.toolbar`): 56px am Telefon, 48px im
 * Querformat, 64px ab `sm`. Weichen sie ab, rutscht die Leiste unter die
 * Kopfzeile oder laesst einen Spalt.
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
  // Nur zwei Dinge haengen an der Stufe: ob inaktive Pillen ihren Namen zeigen
  // und ob die Menge als Zahl in der Pille oder als Marke am Symbol steht.
  const compact = useLayout().isMobile;
  const barRef = useRef<HTMLDivElement>(null);

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
        // Ab Tablet duerfen die Pillen umbrechen – zwei Zeilen sind dort
        // verkraftbar, ein waagerechter Scrollbalken versteckt dagegen Bereiche.
        flexWrap: compact ? 'nowrap' : 'wrap',
        gap: compact ? 0.5 : 1,
        rowGap: 1,
        px: compact ? 0.5 : 0,
        py: 1,
        borderBottom: 1,
        borderColor: 'divider',
        position: 'sticky',
        ...STICKY_TOP,
        // Ohne eigenen Grund scheint der scrollende Inhalt durch die Leiste.
        bgcolor: 'background.default',
        zIndex: (theme) => theme.zIndex.appBar - 1,
        // Enger takten, wo es wirklich eng wird: Bei 320px bleiben nach Seiten-
        // polsterung 288px, von denen vier Symbole samt Abstaenden 176px fressen.
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
            // Am Telefon steht inaktiv nur das Symbol da – der Name muss
            // trotzdem vorgelesen werden.
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
              // Kein `overflow: hidden` auf der Schaltflaeche: Der Name kuerzt
              // sich selbst, die Mengenmarke wuerde hier aber angeschnitten –
              // bei 320px bleiben je Symbol nur ~41px, und "128" ragt darueber.
              color: selected ? 'primary.contrastText' : 'text.secondary',
              // primary.dark statt .main: Weisse Schrift braucht 4,5:1 (WCAG AA,
              // normaler Text). .main erreicht beim Orange-Preset nur ~3,8:1 und
              // liest sich entsprechend blass; .dark raeumt bei allen Presets ab.
              // Dieselbe Rechnung steht in Navigation.tsx fuer den gewaehlten
              // Navigationseintrag.
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
              {/* Bei leerem Bereich keine Null-Marke: fuenf Nullen sind Laerm, keine Information. */}
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
                // Am Telefon faehrt der Name auf, statt hart einzublenden: Die
                // Pille waechst sichtbar aus dem Symbol heraus, das man gerade
                // getippt hat. Ab Tablet steht er ohnehin dauerhaft da.
                maxWidth: compact ? (selected ? '14ch' : 0) : 'none',
                ml: compact && !selected ? 0 : 0.75,
                opacity: compact && !selected ? 0 : 1,
                minWidth: 0,
                overflow: 'hidden',
                whiteSpace: 'nowrap',
                textOverflow: 'ellipsis',
                // Groesse aus dem Thema statt als rem-Literal: Damit folgt die
                // Pille der Schriftgroessen-Umschaltung und landet dabei auf
                // ganzen Pixeln (14px bzw. 16px), statt bei 18px Wurzel auf
                // 15,75px zu rastern.
                fontSize: (theme) => theme.typography.body2.fontSize,
                // 700 statt 600: Roboto liegt nur in 300/400/500/700 vor, 600
                // wuerde der Browser ohnehin auf 700 hochziehen.
                fontWeight: 700,
                lineHeight: 1.2,
                transition: compact ? LABEL_TRANSITION : undefined,
              }}
            >
              {section.label}
            </Box>

            {/* Ab Tablet ist Platz fuer die Menge als Zahl – das ersetzt die Marke. */}
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
