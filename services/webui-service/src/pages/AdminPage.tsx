import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Accordion, AccordionDetails, AccordionSummary,
  Box, Chip, InputAdornment, List, ListItem, ListItemButton, ListItemIcon,
  ListItemText, TextField, Typography,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import SearchIcon from '@mui/icons-material/Search';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';
import { PageShell } from '@/components/common/PageShell';
import { SETTINGS_GROUP_ICONS } from '@/components/admin/settingsIcons';
import { SettingsSection } from '@/components/admin/SettingsSection';
import { SECTION_CONTENT } from '@/config/sectionContent';
import {
  SETTINGS_HEADINGS, SETTINGS_INDEX, SETTINGS_SECTIONS, sectionDomId,
  type SettingsGroupMeta, type SettingsHeadingMeta, type SettingsSectionMeta,
} from '@/config/settingsIndex';
import { useLayout } from '@/hooks/useLayout';
import { useCapabilities } from '@/contexts/CapabilitiesContext';

/** A section with its anchor id - target for deep links from the CommandPalette. */
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

/** Groups that share a heading, in `SETTINGS_HEADINGS` order. A purely
 *  navigational clustering - a group still stands on its own. Headings with
 *  no visible group (none currently can end up that way, but a section list
 *  is always filtered by capability) are dropped rather than shown empty. */
interface HeadingGroup {
  heading: SettingsHeadingMeta;
  groups: SettingsGroupMeta[];
}

const groupByHeading = (groups: SettingsGroupMeta[]): HeadingGroup[] =>
  SETTINGS_HEADINGS.map((heading) => ({
    heading,
    groups: groups.filter((group) => group.headingKey === heading.key),
  })).filter((entry) => entry.groups.length > 0);

interface LayoutProps {
  headings: HeadingGroup[];
  /** `null` = no group chosen yet: desktop shows the first, mobile all collapsed. */
  activeGroupKey: string | null;
  onActiveGroupChange: (key: string | null) => void;
  highlightedSection: string | null;
}

/** 220px: the same width as the app's own navigation drawer
 *  (`Navigation.tsx`) - two nested drawers of different widths would read as
 *  two different systems rather than one page inside the other. */
const SIDEBAR_WIDTH = 220;

const DesktopLayout: React.FC<LayoutProps> = ({
  headings, activeGroupKey, onActiveGroupChange, highlightedSection,
}) => {
  const { t } = useTranslation(['admin', 'setup']);
  const allGroups = headings.flatMap((entry) => entry.groups);
  const activeGroup = allGroups.find((g) => g.key === activeGroupKey) ?? allGroups[0];

  return (
    <Box sx={{ display: 'flex', gap: 4, alignItems: 'flex-start', pt: 1 }}>
      <Box component="nav" aria-label={t('title')} sx={{ width: SIDEBAR_WIDTH, flexShrink: 0 }}>
        {headings.map(({ heading, groups }) => (
          <Box key={heading.key} sx={{ mb: 2 }}>
            <Typography
              variant="overline"
              color="text.secondary"
              sx={{ display: 'block', px: 1.5, mb: 0.5 }}
            >
              {t(heading.labelKey)}
            </Typography>
            <List disablePadding>
              {groups.map((group) => {
                const selected = group.key === activeGroup?.key;
                return (
                  <ListItem key={group.key} disablePadding>
                    <ListItemButton
                      selected={selected}
                      onClick={() => onActiveGroupChange(group.key)}
                      sx={{
                        borderRadius: 2,
                        mb: 0.25,
                        gap: 1.5,
                        '&.Mui-selected': {
                          // Same rule as the primary navigation
                          // (`Navigation.tsx`): white text needs 4.5:1
                          // (WCAG AA), which only `.dark` clears across every
                          // accent preset.
                          backgroundColor: 'primary.dark',
                          color: 'primary.contrastText',
                          '&:hover': { filter: 'brightness(0.85)' },
                          '& .MuiListItemIcon-root': { color: 'primary.contrastText' },
                        },
                      }}
                    >
                      <ListItemIcon sx={{ minWidth: 0, '& svg': { fontSize: 20 } }}>
                        {SETTINGS_GROUP_ICONS[group.key]}
                      </ListItemIcon>
                      <ListItemText
                        primaryTypographyProps={{ fontSize: 14, fontWeight: selected ? 600 : 400 }}
                      >
                        {t(group.labelKey)}
                      </ListItemText>
                    </ListItemButton>
                  </ListItem>
                );
              })}
            </List>
          </Box>
        ))}
      </Box>
      <Box sx={{ flex: 1, minWidth: 0 }}>
        {activeGroup?.sections.map((section) => (
          <RenderedSection
            key={section.key}
            section={section}
            highlighted={highlightedSection === section.key}
          />
        ))}
      </Box>
    </Box>
  );
};

const MobileLayout: React.FC<LayoutProps> = ({
  headings, activeGroupKey, onActiveGroupChange, highlightedSection,
}) => {
  const { t } = useTranslation(['admin', 'setup']);
  return (
    <Box sx={{ mt: 1 }}>
      {headings.map(({ heading, groups }) => (
        <Box key={heading.key} sx={{ mb: 2 }}>
          <Typography
            variant="overline"
            color="text.secondary"
            sx={{ display: 'block', px: 0.5, mb: 0.5 }}
          >
            {t(heading.labelKey)}
          </Typography>
          {groups.map((group) => (
            <Accordion
              key={group.key}
              expanded={activeGroupKey === group.key}
              onChange={(_, isExpanded) => onActiveGroupChange(isExpanded ? group.key : null)}
              // A collapsed group is *gone*, not just hidden. Without this every
              // group renders its panels at once - eleven of them, each with its
              // own API call, on a phone talking to a Raspberry Pi.
              TransitionProps={{ unmountOnExit: true }}
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
                    {/* Says what is in the group before expanding it - the section
                        titles are already translated, no extra text needed. */}
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
      ))}
    </Box>
  );
};

/**
 * Results list of the settings search. Searched over group name, section title
 * and the labels of the contained fields (`searchKeys`), each in the active
 * language - so "MQTT" or "Wi-Fi" finds the section without knowing the group.
 *
 * Deliberately just a jump list instead of the expanded forms: a short
 * input matches almost every section, and mounting them all at once would
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
          {/* Shows *why* the section is in the results, when the title was not the match */}
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

  // Sections that hang off a component that is not installed are dropped -
  // along with the group that becomes empty. Applies to navigation, forms and
  // search alike (one source).
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

  // Jump to a section: open the group, close the search, scroll to it and
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

  const headings = useMemo(() => groupByHeading(visibleGroups), [visibleGroups]);

  const layoutProps: LayoutProps = {
    headings,
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
