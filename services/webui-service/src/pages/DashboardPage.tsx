import React, { useState } from 'react';
import { Box } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { PageShell } from '@/components/common/PageShell';
import { SectionTabs } from '@/components/common/SectionTabs';
import { StatsDashboard } from '@/components/dashboard/StatsDashboard';
import { DashboardOverview } from '@/components/dashboard/DashboardOverview';
import { ScanHistoryPanel } from '@/components/dashboard/ScanHistoryPanel';
import { ChildSettingsForm } from '@/components/dashboard/ChildSettingsForm';

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
      <SectionTabs
        value={tab}
        onChange={setTab}
        ariaLabel={t('navigation.dashboard')}
        labels={[
          t('dashboard.tabs.overview'),
          t('dashboard.tabs.rules'),
          t('dashboard.tabs.stats'),
          t('dashboard.tabs.scan_history'),
        ]}
      />
      <TabPanel value={tab} index={0}>
        <DashboardOverview />
      </TabPanel>
      {/* Regeln stehen bewusst neben der Anzeige, die sie erzeugen (verbleibende Minuten) */}
      <TabPanel value={tab} index={1}>
        <ChildSettingsForm />
      </TabPanel>
      <TabPanel value={tab} index={2}>
        <StatsDashboard />
      </TabPanel>
      <TabPanel value={tab} index={3}>
        <ScanHistoryPanel />
      </TabPanel>
    </PageShell>
  );
};
