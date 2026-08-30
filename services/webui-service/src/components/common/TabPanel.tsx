import React from 'react';
import { Box } from '@mui/material';

interface TabPanelProps {
  children?: React.ReactNode;
  /** Index of this panel. */
  index: number;
  /** Index of the currently selected tab. */
  value: number;
}

/**
 * Content of one tab.
 *
 * Children are mounted only while the tab is selected: the media page would
 * otherwise start the API calls of all five tabs at once, which on a Raspberry
 * Pi is the difference between a page that opens and one that stalls.
 */
export const TabPanel: React.FC<TabPanelProps> = ({ children, value, index }) => (
  <Box role="tabpanel" hidden={value !== index} sx={{ pt: 2 }}>
    {value === index && children}
  </Box>
);
