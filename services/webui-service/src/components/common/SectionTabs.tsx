import React, { useState } from 'react';
import {
  Box,
  ButtonBase,
  Drawer,
  List,
  ListItemButton,
  ListItemText,
  Tab,
  Tabs,
  Typography,
  useMediaQuery,
  useTheme,
} from '@mui/material';
import CheckIcon from '@mui/icons-material/Check';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import { SAFE_AREA_BOTTOM } from '@/components/common/Navigation';

interface SectionTabsProps {
  value: number;
  onChange: (value: number) => void;
  /** Bereichsnamen in Reihenfolge; der Index ist der Tab-Wert. */
  labels: string[];
  /** Screenreader-Bezeichnung der Bereichsauswahl. */
  ariaLabel?: string;
}

/**
 * Bereichsumschaltung einer Seite – Tabs auf dem Desktop, Auswahlliste auf dem
 * Telefon.
 *
 * Hintergrund: MUI gibt jedem `Tab` `minWidth: 90px`. Fuenf Bereiche brauchen
 * damit mindestens 450px; auf einem 390px-Geraet bleiben nach dem Seiten-
 * Padding 366px. Die Leiste lief also zwangslaeufig ueber, und `scrollable`
 * verlangte eine Wischgeste, um ueberhaupt zu *sehen*, dass es weitere
 * Bereiche gibt – die Scroll-Pfeile fressen die knappe Breite zusaetzlich auf.
 *
 * Unterhalb `sm` steht deshalb eine Zeile mit dem aktuellen Bereich und einem
 * Zaehler ("2/5", der die Existenz der anderen Bereiche sichtbar macht); ein
 * Tap oeffnet die vollstaendige Liste als Sheet aus der Daumenzone. Das ist
 * dasselbe Muster, mit dem die Einstellungsseite ihre Gruppen auf Mobil
 * aufklappt, statt sie in eine Tab-Leiste zu zwingen.
 */
export const SectionTabs: React.FC<SectionTabsProps> = ({
  value,
  onChange,
  labels,
  ariaLabel,
}) => {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));
  const [open, setOpen] = useState(false);

  if (!isMobile) {
    return (
      <Tabs
        value={value}
        onChange={(_, v: number) => onChange(v)}
        variant="scrollable"
        scrollButtons="auto"
        aria-label={ariaLabel}
        sx={{ borderBottom: 1, borderColor: 'divider' }}
      >
        {labels.map((label) => (
          <Tab key={label} label={label} />
        ))}
      </Tabs>
    );
  }

  return (
    <>
      <ButtonBase
        onClick={() => setOpen(true)}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={ariaLabel}
        sx={{
          width: '100%',
          minHeight: 48,
          px: 1,
          py: 1.25,
          gap: 1,
          justifyContent: 'space-between',
          textAlign: 'left',
          borderBottom: 1,
          borderColor: 'divider',
        }}
      >
        <Typography variant="subtitle1" fontWeight={600} noWrap>
          {labels[value]}
        </Typography>
        <Box
          sx={{ display: 'flex', alignItems: 'center', gap: 0.5, color: 'text.secondary', flexShrink: 0 }}
        >
          <Typography variant="caption">
            {value + 1}/{labels.length}
          </Typography>
          <ExpandMoreIcon fontSize="small" />
        </Box>
      </ButtonBase>

      <Drawer
        anchor="bottom"
        open={open}
        onClose={() => setOpen(false)}
        PaperProps={{
          sx: {
            borderTopLeftRadius: 16,
            borderTopRightRadius: 16,
            pb: SAFE_AREA_BOTTOM,
          },
        }}
      >
        {/* Griff-Andeutung, damit das Sheet als schliessbar lesbar ist */}
        <Box
          sx={{
            width: 36,
            height: 4,
            borderRadius: 2,
            bgcolor: 'divider',
            mx: 'auto',
            mt: 1,
            mb: 0.5,
          }}
        />
        <List role="listbox" aria-label={ariaLabel}>
          {labels.map((label, index) => (
            <ListItemButton
              key={label}
              role="option"
              aria-selected={index === value}
              selected={index === value}
              onClick={() => {
                onChange(index);
                setOpen(false);
              }}
              sx={{ minHeight: 52 }}
            >
              <ListItemText
                primary={label}
                primaryTypographyProps={{ fontWeight: index === value ? 600 : 400 }}
              />
              {index === value && <CheckIcon fontSize="small" color="primary" />}
            </ListItemButton>
          ))}
        </List>
      </Drawer>
    </>
  );
};
