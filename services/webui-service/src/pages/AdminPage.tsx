import React, { useState } from 'react';
import {
  Box,
  Tab,
  Tabs,
  Typography,
  useMediaQuery,
  useTheme,
} from '@mui/material';
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
  DesignSettingsForm,
  GeneralSettingsForm,
  RFIDConfigForm,
} from '@/components/admin/ConfigForm';

interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}

const TabPanel: React.FC<TabPanelProps> = ({ children, value, index }) => (
  <Box role="tabpanel" hidden={value !== index} sx={{ pt: 3 }}>
    {value === index && children}
  </Box>
);

export const AdminPage: React.FC = () => {
  const { t } = useTranslation('admin');
  const theme = useTheme();
  const isSmall = useMediaQuery(theme.breakpoints.down('sm'));
  const [tab, setTab] = useState(0);
  const [hardwareSubTab, setHardwareSubTab] = useState(0);

  return (
    <PageShell title={t('title')}>
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
            px: isSmall ? 1 : 2,
            fontSize: isSmall ? '0.75rem' : undefined,
            whiteSpace: 'nowrap',
          },
        }}
      >
        <Tab label={t('tabs.status')} />
        <Tab label={t('tabs.system')} />
        <Tab label={t('tabs.hardware')} />
        <Tab label={t('tabs.general')} />
        <Tab label={t('tabs.design')} />
        <Tab label={t('tabs.child')} />
        <Tab label={t('tabs.security')} />
      </Tabs>

      <TabPanel value={tab} index={0}>
        <SystemStatusPanel />
      </TabPanel>
      <TabPanel value={tab} index={1}>
        <SystemPanel />
      </TabPanel>
      <TabPanel value={tab} index={2}>
        <Box sx={{ pt: 0 }}>
          <Tabs
            value={hardwareSubTab}
            onChange={(_, v) => setHardwareSubTab(v)}
            variant="scrollable"
            scrollButtons="auto"
            sx={{
              borderBottom: 1,
              borderColor: 'divider',
              minHeight: 40,
              mb: 2,
              '& .MuiTab-root': { minWidth: 'auto', fontSize: isSmall ? '0.8rem' : undefined },
            }}
          >
            <Tab label={t('tabs.audio')} />
            <Tab label={t('tabs.leds')} />
            <Tab label={t('tabs.buttons')} />
            <Tab label={t('tabs.display')} />
            <Tab label={t('tabs.rfid')} />
          </Tabs>
          <TabPanel value={hardwareSubTab} index={0}>
            <Typography variant="h6" gutterBottom>{t('audio.title')}</Typography>
            <AudioConfigForm />
            <BluetoothSection />
          </TabPanel>
          <TabPanel value={hardwareSubTab} index={1}>
            <Typography variant="h6" gutterBottom>{t('leds.title')}</Typography>
            <LEDConfigPanel />
          </TabPanel>
          <TabPanel value={hardwareSubTab} index={2}>
            <Typography variant="h6" gutterBottom>{t('buttons.title')}</Typography>
            <ButtonConfigPanel />
          </TabPanel>
          <TabPanel value={hardwareSubTab} index={3}>
            <Typography variant="h6" gutterBottom>{t('display.title')}</Typography>
            <DisplayConfigPanel />
          </TabPanel>
          <TabPanel value={hardwareSubTab} index={4}>
            <Typography variant="h6" gutterBottom>{t('rfid.title')}</Typography>
            <RFIDConfigForm />
          </TabPanel>
        </Box>
      </TabPanel>
      <TabPanel value={tab} index={3}>
        <Typography variant="h6" gutterBottom>{t('general.title')}</Typography>
        <GeneralSettingsForm />
      </TabPanel>
      <TabPanel value={tab} index={4}>
        <Typography variant="h6" gutterBottom>{t('design.title')}</Typography>
        <DesignSettingsForm />
      </TabPanel>
      <TabPanel value={tab} index={5}>
        <ChildSettingsForm />
      </TabPanel>
      <TabPanel value={tab} index={6}>
        <SecurityPanel />
      </TabPanel>
    </PageShell>
  );
};
