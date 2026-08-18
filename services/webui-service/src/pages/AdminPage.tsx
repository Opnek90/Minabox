import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Accordion, AccordionDetails, AccordionSummary,
  Box, Chip, InputAdornment, List, ListItemButton, Tab, Tabs, TextField, Typography,
  useMediaQuery, useTheme,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import SearchIcon from '@mui/icons-material/Search';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';
import { PageShell } from '@/components/common/PageShell';
import { SecurityPanel } from '@/components/admin/SecurityPanel';
import { BluetoothSection } from '@/components/admin/BluetoothSection';
import { BoardLedsToggle } from '@/components/admin/BoardLedsToggle';
import { LEDConfigPanel } from '@/components/admin/LEDConfigPanel';
import { ButtonConfigPanel } from '@/components/admin/ButtonConfigPanel';
import { DisplayConfigPanel } from '@/components/admin/DisplayConfigPanel';
import { NetworkPanel } from '@/components/admin/NetworkPanel';
import { UsbImportPanel } from '@/components/admin/UsbImportPanel';
import { SystemMaintenanceSection } from '@/components/admin/SystemMaintenanceSection';
import { SystemStatusPanel } from '@/components/admin/SystemStatus';
import { SettingsSection } from '@/components/admin/SettingsSection';
import {
  AdvancedSettingsForm, AudioConfigForm, DesignSettingsForm,
  MediaPathForm, PlaybackSettingsForm, RFIDConfigForm,
} from '@/components/admin/ConfigForm';
import {
  SETTINGS_INDEX, SETTINGS_SECTIONS, sectionDomId,
  type SettingsGroupMeta, type SettingsSectionMeta,
} from '@/config/settingsIndex';

/**
 * Formular je Section. Der Zuschnitt der Gruppen/Sections selbst liegt in
 * `@/config/settingsIndex`, damit die CommandPalette dieselbe Struktur
 * durchsuchen kann, ohne die React-Inhalte zu kennen.
 */
const SECTION_CONTENT: Record<string, React.ReactNode> = {
  audio: (
    <>
      <AudioConfigForm />
      <BluetoothSection />
    </>
  ),
  playback: <PlaybackSettingsForm />,
  design: <DesignSettingsForm />,
  rfid: <RFIDConfigForm />,
  buttons: <ButtonConfigPanel />,
  leds: (
    <>
      <LEDConfigPanel />
      <BoardLedsToggle />
    </>
  ),
  display: <DisplayConfigPanel />,
  network: <NetworkPanel />,
  media_path: <MediaPathForm />,
  usb: <UsbImportPanel />,
  maintenance: <SystemMaintenanceSection />,
  security: <SecurityPanel />,
  advanced: <AdvancedSettingsForm />,
  diagnose: <SystemStatusPanel />,
};

/** Section samt Anker-Id – Ziel für Deep-Links aus der CommandPalette. */
const RenderedSection: React.FC<{ section: SettingsSectionMeta; highlighted?: boolean }> = ({
  section,
  highlighted,
}) => {
  const { t } = useTranslation('admin');
  return (
    <Box
      id={sectionDomId(section.key)}
      sx={{
        scrollMarginTop: 80,
        borderRadius: 1,
        transition: 'box-shadow 0.4s',
        boxShadow: highlighted ? (theme) => `0 0 0 2px ${theme.palette.primary.main}` : 'none',
      }}
    >
      <SettingsSection title={t(section.titleKey)}>
        {SECTION_CONTENT[section.key] ?? null}
      </SettingsSection>
    </Box>
  );
};

interface LayoutProps {
  groups: SettingsGroupMeta[];
  /** `null` = noch keine Gruppe gewählt: Desktop zeigt die erste, Mobile alle zugeklappt. */
  activeGroupKey: string | null;
  onActiveGroupChange: (key: string | null) => void;
  highlightedSection: string | null;
}

const DesktopLayout: React.FC<LayoutProps> = ({
  groups, activeGroupKey, onActiveGroupChange, highlightedSection,
}) => {
  const { t } = useTranslation('admin');
  const tabIndex = Math.max(0, groups.findIndex((g) => g.key === activeGroupKey));
  const activeGroup = groups[tabIndex];
  return (
    <>
      <Tabs
        value={tabIndex}
        onChange={(_, v: number) => onActiveGroupChange(groups[v].key)}
        variant="scrollable"
        scrollButtons="auto"
        allowScrollButtonsMobile
        visibleScrollbar
        sx={{
          borderBottom: 1, borderColor: 'divider', minHeight: 48,
          '& .MuiTab-root': { minWidth: 'auto', px: 2, whiteSpace: 'nowrap' },
        }}
      >
        {groups.map((g) => <Tab key={g.key} label={t(g.labelKey)} />)}
      </Tabs>
      <Box sx={{ pt: 3 }}>
        {activeGroup.sections.map((section) => (
          <RenderedSection
            key={section.key}
            section={section}
            highlighted={highlightedSection === section.key}
          />
        ))}
      </Box>
    </>
  );
};

const MobileLayout: React.FC<LayoutProps> = ({
  groups, activeGroupKey, onActiveGroupChange, highlightedSection,
}) => {
  const { t } = useTranslation('admin');
  return (
    <Box sx={{ mt: 1 }}>
      {groups.map((group) => (
        <Accordion
          key={group.key}
          expanded={activeGroupKey === group.key}
          onChange={(_, isExpanded) => onActiveGroupChange(isExpanded ? group.key : null)}
          disableGutters
          sx={{
            '&:before': { display: 'none' },
            border: 1, borderColor: 'divider', borderRadius: 1, mb: 1,
            '&.Mui-expanded': { mb: 1 },
          }}
        >
          <AccordionSummary
            expandIcon={<ExpandMoreIcon />}
            sx={{ minHeight: 52, '& .MuiAccordionSummary-content': { my: 1 } }}
          >
            <Typography variant="subtitle1" fontWeight={600}>{t(group.labelKey)}</Typography>
          </AccordionSummary>
          <AccordionDetails sx={{ pt: 1, pb: 2, px: 2 }}>
            {group.sections.map((section) => (
              <RenderedSection
                key={section.key}
                section={section}
                highlighted={highlightedSection === section.key}
              />
            ))}
          </AccordionDetails>
        </Accordion>
      ))}
    </Box>
  );
};

/**
 * Trefferliste der Settings-Suche. Gesucht wird über Gruppenname, Section-Titel
 * und die Labels der enthaltenen Felder (`searchKeys`), jeweils in der aktiven
 * Sprache – damit findet „MQTT" oder „WLAN" die Section, ohne dass man die
 * Gruppe kennt.
 *
 * Bewusst nur eine Sprungliste statt der ausgeklappten Formulare: eine kurze
 * Eingabe trifft fast alle Sections, und die gleichzeitig zu mounten würde auf
 * dem Pi elf Panels samt ihrer API-Calls auf einmal starten.
 */
const SearchResults: React.FC<{ query: string; onSelect: (sectionKey: string) => void }> = ({
  query,
  onSelect,
}) => {
  const { t } = useTranslation('admin');
  const q = query.trim().toLowerCase();

  const matches = useMemo(
    () =>
      SETTINGS_SECTIONS.map((section) => {
        const groupLabel = t(section.groupLabelKey);
        const sectionTitle = t(section.titleKey);
        const matchedFields = section.searchKeys
          .map((key) => t(key))
          .filter((label) => label.toLowerCase().includes(q));
        const titleMatch =
          groupLabel.toLowerCase().includes(q) || sectionTitle.toLowerCase().includes(q);
        return { section, matchedFields, hit: titleMatch || matchedFields.length > 0 };
      }).filter((m) => m.hit),
    [q, t]
  );

  if (matches.length === 0) {
    return (
      <Box sx={{ pt: 3, textAlign: 'center' }}>
        <Typography color="text.secondary">
          {t('search.no_results', { defaultValue: 'Keine Einstellungen gefunden.' })}
        </Typography>
      </Box>
    );
  }

  return (
    <List sx={{ pt: 1 }}>
      {matches.map(({ section, matchedFields }) => (
        <ListItemButton
          key={section.key}
          onClick={() => onSelect(section.key)}
          sx={{ borderRadius: 1, mb: 0.5, alignItems: 'flex-start', flexDirection: 'column' }}
        >
          <Box display="flex" alignItems="center" gap={1} flexWrap="wrap">
            <Typography variant="body2" fontWeight={600}>
              {t(section.titleKey)}
            </Typography>
            <Chip label={t(section.groupLabelKey)} size="small" variant="outlined" />
          </Box>
          {/* Zeigt, *warum* die Section im Ergebnis steht, wenn nicht der Titel getroffen hat */}
          {matchedFields.length > 0 && (
            <Typography variant="caption" color="text.secondary" sx={{ mt: 0.25 }}>
              {matchedFields.slice(0, 4).join(' · ')}
            </Typography>
          )}
        </ListItemButton>
      ))}
    </List>
  );
};

export const AdminPage: React.FC = () => {
  const { t } = useTranslation('admin');
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));
  const [searchParams, setSearchParams] = useSearchParams();
  const [query, setQuery] = useState('');
  const [activeGroupKey, setActiveGroupKey] = useState<string | null>(null);
  const [highlightedSection, setHighlightedSection] = useState<string | null>(null);
  const isSearching = query.trim().length > 0;

  // Eine Section anspringen: Gruppe öffnen, Suche schließen, hinscrollen und
  // kurz hervorheben. Wird von der Trefferliste und vom Deep-Link genutzt.
  const jumpToSection = useCallback((sectionKey: string) => {
    const target = SETTINGS_SECTIONS.find((s) => s.key === sectionKey);
    if (!target) return;
    setActiveGroupKey(target.groupKey);
    setQuery('');
    setHighlightedSection(target.key);
    // Erst nach dem Re-Render existiert der Anker im DOM.
    window.setTimeout(() => {
      document.getElementById(sectionDomId(target.key))?.scrollIntoView({
        behavior: 'smooth',
        block: 'start',
      });
    }, 100);
    window.setTimeout(() => setHighlightedSection(null), 2500);
  }, []);

  // Deep-Link `/admin?section=<key>`, z. B. aus der CommandPalette.
  const deepLinkSection = searchParams.get('section');
  useEffect(() => {
    if (!deepLinkSection) return;
    jumpToSection(deepLinkSection);
    searchParams.delete('section');
    setSearchParams(searchParams, { replace: true });
  }, [deepLinkSection, jumpToSection, searchParams, setSearchParams]);

  const layoutProps: LayoutProps = {
    groups: SETTINGS_INDEX,
    activeGroupKey,
    onActiveGroupChange: setActiveGroupKey,
    highlightedSection,
  };

  return (
    <PageShell title={t('title')}>
      <TextField
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder={t('search.placeholder', { defaultValue: 'Einstellungen durchsuchen…' })}
        size="small"
        fullWidth
        sx={{ mb: 2 }}
        InputProps={{
          startAdornment: (
            <InputAdornment position="start">
              <SearchIcon fontSize="small" color="action" />
            </InputAdornment>
          ),
        }}
      />
      {isSearching ? (
        <SearchResults query={query} onSelect={jumpToSection} />
      ) : isMobile ? (
        <MobileLayout {...layoutProps} />
      ) : (
        <DesktopLayout {...layoutProps} />
      )}
    </PageShell>
  );
};
