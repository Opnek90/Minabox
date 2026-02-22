import React, { useState } from 'react';
import { Box, Tab, Tabs } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { PageShell } from '@/components/common/PageShell';
import { StatsDashboard } from '@/components/admin/StatsDashboard';
import { ParentSettingsForm } from '@/components/dashboard/ParentSettingsForm';

interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}

const TabPanel: React.FC<TabPanelProps> = ({ children, value, index }) => (
  <Box role="tabpanel" hidden={value !== index} sx={{ pt: 2 }}>
    {value === index && children}
  </Box>
);

export const DashboardPage: React.FC = () => {
  const { t } = useTranslation('common');
  const [tab, setTab] = useState(0);

  return (
    <PageShell title={t('navigation.dashboard')}>
      <Tabs
        value={tab}
        onChange={(_, v) => setTab(v)}
        sx={{ borderBottom: 1, borderColor: 'divider', mb: 0 }}
      >
        <Tab label={t('dashboard.tabs.stats')} />
        <Tab label={t('dashboard.tabs.settings')} />
      </Tabs>
      <TabPanel value={tab} index={0}>
        <StatsDashboard />
      </TabPanel>
      <TabPanel value={tab} index={1}>
        <ParentSettingsForm />
      </TabPanel>
    </PageShell>
  );
};
