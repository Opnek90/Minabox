import React, { useState } from 'react';
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Box,
  Tab,
  Tabs,
  Typography,
  useMediaQuery,
  useTheme,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import { useTranslation } from 'react-i18next';
import { PageShell } from '@/components/common/PageShell';
import { SystemStatusPanel } from '@/components/admin/SystemStatus';
import { SystemPanel } from '@/components/admin/SystemPanel';
import { SecurityPanel } from '@/components/admin/SecurityPanel';
import { BluetoothSection } from '@/components/admin/BluetoothSection';
import { LEDConfigPanel } from '@/components/admin/LEDConfigPanel';
import { ButtonConfigPanel } from '@/components/admin/ButtonConfigPanel';
import { DisplayConfigPanel } from '@/components/admin/DisplayConfigPanel';
import { ChildSettingsForm } from '@/components/admin/ChildSettingsForm';
import {
  AudioConfigForm,
  ControlSettingsForm,
  DesignSettingsForm,
  GeneralSettingsForm,
  RFIDConfigForm,
} from '@/components/admin/ConfigForm';

// ---------------------------------------------------------------------------
// Group definitions — single source of truth for both layouts
// ---------------------------------------------------------------------------

interface SettingsSection {
  key: string;
  titleKey: string;
  content: React.ReactNode;
}

interface SettingsGroup {
  key: string;
  labelKey: string;
  sections: SettingsSection[];
}

const useSettingsGroups = (): SettingsGroup[] => {
  const { t } = useTranslation('admin');

  return [
    // ── Group 1: Child & Profile ──────────────────────────────────────────
    {
      key: 'child',
      labelKey: 'groups.child',
      sections: [
        {
          key: 'child_settings',
          titleKey: 'child.title',
          content: <ChildSettingsForm />,
        },
        {
          key: 'control',
          titleKey: 'control.title',
          content: (
            <>
              <Typography variant="h6" gutterBottom>{t('control.title')}</Typography>
              <ControlSettingsForm />
            </>
          ),
        },
        {
          key: 'design',
          titleKey: 'design.title',
          content: (
            <>
              <Typography variant="h6" gutterBottom>{t('design.title')}</Typography>
              <DesignSettingsForm />
            </>
          ),
        },
      ],
    },

    // ── Group 2: Media Playback ───────────────────────────────────────────
    {
      key: 'media',
      labelKey: 'groups.media',
      sections: [
        {
          key: 'audio',
          titleKey: 'audio.title',
          content: (
            <>
              <Typography variant="h6" gutterBottom>{t('audio.title')}</Typography>
              <AudioConfigForm />
              <BluetoothSection />
            </>
          ),
        },
        {
          key: 'general',
          titleKey: 'general.title',
          content: (
            <>
              <Typography variant="h6" gutterBottom>{t('general.title')}</Typography>
              <GeneralSettingsForm />
            </>
          ),
        },
      ],
    },

    // ── Group 3: RFID & Hardware ──────────────────────────────────────────
    {
      key: 'hardware',
      labelKey: 'groups.hardware',
      sections: [
        {
          key: 'rfid',
          titleKey: 'rfid.title',
          content: (
            <>
              <Typography variant="h6" gutterBottom>{t('rfid.title')}</Typography>
              <RFIDConfigForm />
            </>
          ),
        },
        {
          key: 'buttons',
          titleKey: 'buttons.title',
          content: (
            <>
              <Typography variant="h6" gutterBottom>{t('buttons.title')}</Typography>
              <ButtonConfigPanel />
            </>
          ),
        },
        {
          key: 'leds',
          titleKey: 'leds.title',
          content: (
            <>
              <Typography variant="h6" gutterBottom>{t('leds.title')}</Typography>
              <LEDConfigPanel />
            </>
          ),
        },
        {
          key: 'display',
          titleKey: 'display.title',
          content: (
            <>
              <Typography variant="h6" gutterBottom>{t('display.title')}</Typography>
              <DisplayConfigPanel />
            </>
          ),
        },
      ],
    },

    // ── Group 4: System & Security ────────────────────────────────────────
    {
      key: 'system',
      labelKey: 'groups.system',
      sections: [
        {
          key: 'status',
          titleKey: 'status.title',
          content: <SystemStatusPanel />,
        },
        {
          key: 'system_panel',
          titleKey: 'system.title',
          content: <SystemPanel />,
        },
        {
          key: 'security',
          titleKey: 'security.title',
          content: <SecurityPanel />,
        },
      ],
    },
  ];
};

// ---------------------------------------------------------------------------
// Desktop layout — 4 top-level tabs, sections stacked vertically inside
// ---------------------------------------------------------------------------

interface DesktopLayoutProps {
  groups: SettingsGroup[];
}

const DesktopLayout: React.FC<DesktopLayoutProps> = ({ groups }) => {
  const { t } = useTranslation('admin');
  const [tab, setTab] = useState(0);
  const activeGroup = groups[tab];

  return (
    <>
      <Tabs
        value={tab}
        onChange={(_, v) => setTab(v)}
        variant="scrollable"
        scrollButtons="auto"
        allowScrollButtonsMobile
        visibleScrollbar
        sx={{
          borderBottom: 1,
          borderColor: 'divider',
          minHeight: 48,
          '& .MuiTab-root': {
            minWidth: 'auto',
            px: 2,
            whiteSpace: 'nowrap',
          },
        }}
      >
        {groups.map((g) => (
          <Tab key={g.key} label={t(g.labelKey)} />
        ))}
      </Tabs>

      <Box sx={{ pt: 3 }}>
        {activeGroup.sections.map((section) => (
          <Box key={section.key} sx={{ mb: 4 }}>
            {section.content}
          </Box>
        ))}
      </Box>
    </>
  );
};

// ---------------------------------------------------------------------------
// Mobile layout — all groups as accordion, sections stacked inside each group
// ---------------------------------------------------------------------------

interface MobileLayoutProps {
  groups: SettingsGroup[];
}

const MobileLayout: React.FC<MobileLayoutProps> = ({ groups }) => {
  const { t } = useTranslation('admin');
  const [expanded, setExpanded] = useState<string | false>(false);

  const handleChange = (panel: string) => (_: React.SyntheticEvent, isExpanded: boolean) => {
    setExpanded(isExpanded ? panel : false);
  };

  return (
    <Box sx={{ mt: 1 }}>
      {groups.map((group) => (
        <Accordion
          key={group.key}
          expanded={expanded === group.key}
          onChange={handleChange(group.key)}
          disableGutters
          sx={{
            '&:before': { display: 'none' },
            border: 1,
            borderColor: 'divider',
            borderRadius: 1,
            mb: 1,
            '&.Mui-expanded': { mb: 1 },
          }}
        >
          <AccordionSummary
            expandIcon={<ExpandMoreIcon />}
            sx={{ minHeight: 52, '& .MuiAccordionSummary-content': { my: 1 } }}
          >
            <Typography variant="subtitle1" fontWeight={600}>
              {t(group.labelKey)}
            </Typography>
          </AccordionSummary>
          <AccordionDetails sx={{ pt: 1, pb: 2, px: 2 }}>
            {group.sections.map((section) => (
              <Box key={section.key} sx={{ mb: 3 }}>
                {section.content}
              </Box>
            ))}
          </AccordionDetails>
        </Accordion>
      ))}
    </Box>
  );
};

// ---------------------------------------------------------------------------
// AdminPage — picks layout based on breakpoint
// ---------------------------------------------------------------------------

export const AdminPage: React.FC = () => {
  const { t } = useTranslation('admin');
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));
  const groups = useSettingsGroups();

  return (
    <PageShell title={t('title')}>
      {isMobile ? (
        <MobileLayout groups={groups} />
      ) : (
        <DesktopLayout groups={groups} />
      )}
    </PageShell>
  );
};
