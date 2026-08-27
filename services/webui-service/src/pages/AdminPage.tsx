import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Accordion, AccordionDetails, AccordionSummary,
  Box, Chip, InputAdornment, List, ListItemButton, TextField, Typography,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import SearchIcon from '@mui/icons-material/Search';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';
import { PageShell } from '@/components/common/PageShell';
import { SectionTabs } from '@/components/common/SectionTabs';
import { SETTINGS_GROUP_ICONS } from '@/components/admin/settingsIcons';
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
  AdvancedSettingsForm, AudioConfigForm, DesignSettingsForm, MediaImportDomainsForm, MediaPathForm,
  PlaybackSettingsForm, RFIDConfigForm, SleepTimerSettingsForm, UploadLimitForm,
} from '@/components/admin/ConfigForm';
import {
  SETTINGS_INDEX, SETTINGS_SECTIONS, sectionDomId,
  type SettingsGroupMeta, type SettingsSectionMeta,
} from '@/config/settingsIndex';
import { useLayout } from '@/hooks/useLayout';
import { useCapabilities } from '@/contexts/CapabilitiesContext';

/**
 * Formular je Section. Der Zuschnitt der Gruppen/Sections selbst liegt in
 * `@/config/settingsIndex`, damit die CommandPalette dieselbe Struktur
 * durchsuchen kann, ohne die React-Inhalte zu kennen.
 */
import { SetupWizardRestart } from '@/components/admin/SetupWizardRestart';

const SECTION_CONTENT: Record<string, React.ReactNode> = {
  audio: (
    <>
      <AudioConfigForm />
      <BluetoothSection />
    </>
  ),
  playback: <PlaybackSettingsForm />,
  sleep: <SleepTimerSettingsForm />,
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
  upload_limit: <UploadLimitForm />,
  media_import_domains: <MediaImportDomainsForm />,
  usb: <UsbImportPanel />,
  maintenance: <SystemMaintenanceSection />,
  security: <SecurityPanel />,
  advanced: <AdvancedSettingsForm />,
  setup_wizard: <SetupWizardRestart />,
  diagnose: <SystemStatusPanel />,
};

/** Section samt Anker-Id – Ziel für Deep-Links aus der CommandPalette. */
const RenderedSection: React.FC<{ section: SettingsSectionMeta; highlighted?: boolean }> = ({
  section,
  highlighted,
}) => {
  const { t } = useTranslation(['admin', 'setup']);
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
  const { t } = useTranslation(['admin', 'setup']);
  const tabIndex = Math.max(0, groups.findIndex((g) => g.key === activeGroupKey));
  const activeGroup = groups[tabIndex];
  return (
    <>
      <SectionTabs
        value={tabIndex}
        onChange={(v) => onActiveGroupChange(groups[v].key)}
        ariaLabel={t('title')}
        sections={groups.map((g) => ({
          label: t(g.labelKey),
          icon: SETTINGS_GROUP_ICONS[g.key],
        }))}
      />
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
  const { t } = useTranslation(['admin', 'setup']);
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
            sx={{ minHeight: 56, '& .MuiAccordionSummary-content': { my: 1, minWidth: 0 } }}
          >
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, minWidth: 0 }}>
              <Box sx={{ display: 'flex', color: 'text.secondary', '& svg': { fontSize: 22 } }}>
                {SETTINGS_GROUP_ICONS[group.key]}
              </Box>
              <Box sx={{ minWidth: 0 }}>
                <Typography variant="subtitle1" fontWeight={600}>{t(group.labelKey)}</Typography>
                {/* Sagt vor dem Aufklappen, was in der Gruppe steckt – die
                    Section-Titel sind bereits uebersetzt, es braucht keine
                    zusaetzlichen Texte. */}
                <Typography variant="caption" color="text.secondary" display="block" noWrap>
                  {group.sections.map((section) => t(section.titleKey)).join(' \u00b7 ')}
                </Typography>
              </Box>
            </Box>
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
const SearchResults: React.FC<{
  query: string;
  sections: typeof SETTINGS_SECTIONS;
  onSelect: (sectionKey: string) => void;
}> = ({ query, sections, onSelect }) => {
  const { t } = useTranslation(['admin', 'setup']);
  const q = query.trim().toLowerCase();

  const matches = useMemo(
    () =>
      sections.map((section) => {
        const groupLabel = t(section.groupLabelKey);
        const sectionTitle = t(section.titleKey);
        const matchedFields = section.searchKeys
          .map((key) => t(key))
          .filter((label) => label.toLowerCase().includes(q));
        const titleMatch =
          groupLabel.toLowerCase().includes(q) || sectionTitle.toLowerCase().includes(q);
        return { section, matchedFields, hit: titleMatch || matchedFields.length > 0 };
      }).filter((m) => m.hit),
    [q, t, sections]
  );

  if (matches.length === 0) {
    return (
      <Box sx={{ pt: 3, textAlign: 'center' }}>
        <Typography color="text.secondary">
          {t('search.no_results')}
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
  const { t } = useTranslation(['admin', 'setup']);
  const isMobile = useLayout().isMobile;
  const { capabilities } = useCapabilities();
  const [searchParams, setSearchParams] = useSearchParams();

  // Abschnitte, die an einer nicht installierten Komponente haengen, ganz
  // weglassen - samt der Gruppe, die dadurch leer wird. Gilt fuer Navigation,
  // Formulare und Suche gleichermassen (eine Quelle).
  const visibleGroups = useMemo<SettingsGroupMeta[]>(
    () =>
      SETTINGS_INDEX.map((group) => ({
        ...group,
        sections: group.sections.filter(
          (section) =>
            !section.requiresFeature ||
            capabilities[section.requiresFeature]?.installed !== false,
        ),
      })).filter((group) => group.sections.length > 0),
    [capabilities],
  );
  const visibleSections = useMemo(
    () =>
      visibleGroups.flatMap((group) =>
        group.sections.map((section) => ({
          ...section,
          groupKey: group.key,
          groupLabelKey: group.labelKey,
        })),
      ),
    [visibleGroups],
  );
  const [query, setQuery] = useState('');
  const [activeGroupKey, setActiveGroupKey] = useState<string | null>(null);
  const [highlightedSection, setHighlightedSection] = useState<string | null>(null);
  const isSearching = query.trim().length > 0;

  // Eine Section anspringen: Gruppe öffnen, Suche schließen, hinscrollen und
  // kurz hervorheben. Wird von der Trefferliste und vom Deep-Link genutzt.
  const jumpToSection = useCallback((sectionKey: string) => {
    const target = visibleSections.find((s) => s.key === sectionKey);
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
  }, [visibleSections]);

  // Deep-Link `/admin?section=<key>`, z. B. aus der CommandPalette.
  const deepLinkSection = searchParams.get('section');
  useEffect(() => {
    if (!deepLinkSection) return;
    jumpToSection(deepLinkSection);
    searchParams.delete('section');
    setSearchParams(searchParams, { replace: true });
  }, [deepLinkSection, jumpToSection, searchParams, setSearchParams]);

  const layoutProps: LayoutProps = {
    groups: visibleGroups,
    activeGroupKey,
    onActiveGroupChange: setActiveGroupKey,
    highlightedSection,
  };

  return (
    <PageShell title={t('title')}>
      <TextField
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder={t('search.placeholder')}
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
        <SearchResults query={query} sections={visibleSections} onSelect={jumpToSection} />
      ) : isMobile ? (
        <MobileLayout {...layoutProps} />
      ) : (
        <DesktopLayout {...layoutProps} />
      )}
    </PageShell>
  );
};
