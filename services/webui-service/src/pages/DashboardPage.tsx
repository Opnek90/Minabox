import React, { useState } from 'react';
import GridViewIcon from '@mui/icons-material/GridView';
import HistoryIcon from '@mui/icons-material/History';
import InsightsIcon from '@mui/icons-material/Insights';
import ScheduleIcon from '@mui/icons-material/Schedule';
import { useTranslation } from 'react-i18next';
import { PageShell } from '@/components/common/PageShell';
import { SectionTabs } from '@/components/common/SectionTabs';
import { StatsDashboard } from '@/components/dashboard/StatsDashboard';
import { DashboardOverview } from '@/components/dashboard/DashboardOverview';
import { ScanHistoryPanel } from '@/components/dashboard/ScanHistoryPanel';
import { ChildSettingsForm } from '@/components/dashboard/ChildSettingsForm';
import { TabPanel } from '@/components/common/TabPanel';

export const DashboardPage: React.FC = () => {
  const { t } = useTranslation('common');
  const [tab, setTab] = useState(0);

  return (
    <PageShell title={t('navigation.dashboard')}>
      <SectionTabs
        value={tab}
        onChange={setTab}
        ariaLabel={t('navigation.dashboard')}
        sections={[
          { label: t('dashboard.tabs.overview'), icon: <GridViewIcon /> },
          { label: t('dashboard.tabs.rules'), icon: <ScheduleIcon /> },
          { label: t('dashboard.tabs.stats'), icon: <InsightsIcon /> },
          { label: t('dashboard.tabs.scan_history'), icon: <HistoryIcon /> },
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
