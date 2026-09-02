import React from 'react';
import { Box, Chip, FormControlLabel, Switch, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { pickText, type ComponentEntry } from '@/api/components';

/**
 * One entry of the component catalogue.
 *
 * The catalogue also lists what this box does *not* have (#181), so an entry
 * has to answer three questions on its own: what does this do, what do I need
 * for it, and what would I get. Name and description come from the backend
 * (`component_catalog.py`), which is what lets a component that is newer than
 * this WebUI release show up as itself; the locale texts stay as the fallback
 * for a box whose backend is older than this page.
 *
 * The switch is a wish, not a command: nothing happens until "apply" in the
 * block above.
 */
interface ComponentCatalogEntryProps {
  entry: ComponentEntry;
  /** Whether the switch is on - the *wanted* state, not the current one. */
  checked: boolean;
  disabled: boolean;
  /** A line above this entry - set for every entry but the first. */
  divider: boolean;
  onToggle: (on: boolean) => void;
}

export const ComponentCatalogEntry: React.FC<ComponentCatalogEntryProps> = ({
  entry,
  checked,
  disabled,
  divider,
  onToggle,
}) => {
  const { t, i18n } = useTranslation('admin');

  // Backend before locale, for both name and description: that is what makes
  // a component the backend knows but this WebUI release does not appear as
  // itself rather than as a raw translation key.
  const name =
    pickText(entry.name, i18n.language) ??
    t(`system.component_${entry.profile}` as never);
  const summary =
    pickText(entry.summary, i18n.language) ??
    t(`system.component_${entry.profile}_hint` as never);
  const hardware = pickText(entry.hardware, i18n.language);

  const stateLabel = (): string => {
    if (!entry.installed) return t('system.components_state_off');
    if (entry.healthy) return t('system.components_state_running');
    if (entry.running) return t('system.components_state_unhealthy');
    return t('system.components_state_stopped');
  };

  const stateColor = (): 'success' | 'warning' | 'default' => {
    if (!entry.installed) return 'default';
    return entry.healthy ? 'success' : 'warning';
  };

  // What is on the box, or - for a component that is not installed - what
  // adding it would bring. Without an update check ever having run, neither is
  // known, and then the line is simply left out.
  const version = entry.installed ? entry.version : entry.latest;
  const versionLabel = entry.installed
    ? t('system.components_version', { version })
    : t('system.components_version_available', { version });

  return (
    <Box
      sx={{
        py: 1,
        ...(divider && { borderTop: 1, borderColor: 'divider' }),
      }}
    >
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <FormControlLabel
          sx={{ flexGrow: 1, mr: 0 }}
          control={
            <Switch
              checked={checked}
              onChange={(_, on) => onToggle(on)}
              disabled={disabled}
              color="primary"
            />
          }
          label={name}
        />
        <Chip size="small" variant="outlined" color={stateColor()} label={stateLabel()} />
      </Box>

      {/* Indented to the label above, so the text belongs to its switch and
          not to the row below it. */}
      <Box sx={{ pl: { xs: 0, sm: 6 }, pb: 0.5 }}>
        <Typography variant="body2" color="text.secondary">
          {summary}
        </Typography>
        {hardware && (
          <Typography variant="caption" color="text.secondary" display="block">
            {t('system.components_needs_hardware', { text: hardware })}
          </Typography>
        )}
        {entry.network && (
          <Typography variant="caption" color="text.secondary" display="block">
            {t('system.components_needs_network')}
          </Typography>
        )}
        {version && (
          <Typography variant="caption" color="text.secondary" display="block">
            {versionLabel}
          </Typography>
        )}
      </Box>
    </Box>
  );
};
