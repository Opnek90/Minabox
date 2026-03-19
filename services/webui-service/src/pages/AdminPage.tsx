import React, { useState } from 'react';
import {
  Accordion, AccordionDetails, AccordionSummary,
  Box, Tab, Tabs, Typography,
  useMediaQuery, useTheme,
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
import { SettingsSection } from '@/components/admin/SettingsSection';
import {
  AudioConfigForm, ControlSettingsForm, DesignSettingsForm,
  GeneralSettingsForm, RFIDConfigForm,
} from '@/components/admin/ConfigForm';

interface SettingsSectionDef {
  key: string;
  titleKey: string;
  content: React.ReactNode;
}

interface SettingsGroup {
  key: string;
  labelKey: string;
  sections: SettingsSectionDef[];
}

const useSettingsGroups = (): SettingsGroup[] => {
  const { t } = useTranslation('admin');
  return [
    {
      key: 'child',
      labelKey: 'groups.child',
      sections: [
        {
          key: 'child_settings',
          titleKey: 'child.title',
          content: (
            <SettingsSection title={t('child.title')}>
              <ChildSettingsForm />
            </SettingsSection>
          ),
        },
        {
          key: 'control',
          titleKey: 'control.title',
          content: (
            <SettingsSection title={t('control.title')}>
              <ControlSettingsForm />
            </SettingsSection>
          ),
        },
        {
          key: 'design',
          titleKey: 'design.title',
          content: (
            <SettingsSection title={t('design.title')}>
              <DesignSettingsForm />
            </SettingsSection>
          ),
        },
      ],
    },
    {
      key: 'media',
      labelKey: 'groups.media',
      sections: [
        {
          key: 'audio',
          titleKey: 'audio.title',
          content: (
            <SettingsSection title={t('audio.title')}>
              <AudioConfigForm />
              <BluetoothSection />
            </SettingsSection>
          ),
        },
        {
          key: 'general',
          titleKey: 'general.title',
          content: (
            <SettingsSection title={t('general.title')}>
              <GeneralSettingsForm />
            </SettingsSection>
          ),
        },
      ],
    },
    {
      key: 'hardware',
      labelKey: 'groups.hardware',
      sections: [
        {
          key: 'rfid',
          titleKey: 'rfid.title',
          content: (
            <SettingsSection title={t('rfid.title')}>
              <RFIDConfigForm />
            </SettingsSection>
          ),
        },
        {
          key: 'buttons',
          titleKey: 'buttons.title',
          content: (
            <SettingsSection title={t('buttons.title')}>
              <ButtonConfigPanel />
            </SettingsSection>
          ),
        },
        {
          key: 'leds',
          titleKey: 'leds.title',
          content: (
            <SettingsSection title={t('leds.title')}>
              <LEDConfigPanel />
            </SettingsSection>
          ),
        },
        {
          key: 'display',
          titleKey: 'display.title',
          content: (
            <SettingsSection title={t('display.title')}>
              <DisplayConfigPanel />
            </SettingsSection>
          ),
        },
      ],
    },
    {
      key: 'system',
      labelKey: 'groups.system',
      sections: [
        {
          key: 'status',
          titleKey: 'status.title',
          content: (
            <SettingsSection title={t('status.title')}>
              <SystemStatusPanel />
            </SettingsSection>
          ),
        },
        {
          key: 'system_panel',
          titleKey: 'system.title',
          content: (
            <SettingsSection title={t('system.title')}>
              <SystemPanel />
            </SettingsSection>
          ),
        },
        {
          key: 'security',
          titleKey: 'security.title',
          content: (
            <SettingsSection title={t('security.title')}>
              <SecurityPanel />
            </SettingsSection>
          ),
        },
      ],
    },
  ];
};

const DesktopLayout: React.FC<{ groups: SettingsGroup[] }> = ({ groups }) => {
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
          borderBottom: 1, borderColor: 'divider', minHeight: 48,
          '& .MuiTab-root': { minWidth: 'auto', px: 2, whiteSpace: 'nowrap' },
        }}
      >
        {groups.map((g) => <Tab key={g.key} label={t(g.labelKey)} />)}
      </Tabs>
      <Box sx={{ pt: 3 }}>
        {activeGroup.sections.map((section) => (
          <Box key={section.key}>{section.content}</Box>
        ))}
      </Box>
    </>
  );
};

const MobileLayout: React.FC<{ groups: SettingsGroup[] }> = ({ groups }) => {
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
              <Box key={section.key}>{section.content}</Box>
            ))}
          </AccordionDetails>
        </Accordion>
      ))}
    </Box>
  );
};

export const AdminPage: React.FC = () => {
  const { t } = useTranslation('admin');
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));
  const groups = useSettingsGroups();
  return (
    <PageShell title={t('title')}>
      {isMobile ? <MobileLayout groups={groups} /> : <DesktopLayout groups={groups} />}
    </PageShell>
  );
};
