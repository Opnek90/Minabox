import React from 'react';
import {
  Box,
  Chip,
  Stack,
  Switch,
  TableCell,
  TableRow,
  Tooltip,
  Typography,
} from '@mui/material';
import SettingsIcon from '@mui/icons-material/Settings';
import SystemUpdateAltIcon from '@mui/icons-material/SystemUpdateAlt';
import { useTranslation } from 'react-i18next';
import { pickText, isSettingAddon, type AddonEntry } from '@/api/addons';
import { ActionButton } from '@/components/ui/ActionButton';

/**
 * One row of the addons table.
 *
 * The table also lists what this box does *not* have (#181), so a row has to
 * answer three questions on its own: what does this do, what do I need for it,
 * and what would I get. Name and description come from the backend
 * (`component_catalog.py`), which is what lets an addon that is newer than
 * this WebUI release show up as itself; the locale texts stay as the fallback
 * for a box whose backend is older than this page.
 *
 * The switch of a compose addon is a wish, not a command: nothing happens
 * until "apply" in the panel around this row, because one press means removing
 * and recreating containers. An addon that is only a setting has no such run -
 * its switch is the setting, and it is written straight away.
 */
interface AddonRowProps {
  entry: AddonEntry;
  /** Whether the switch is on - the *wanted* state, not the current one. */
  checked: boolean;
  disabled: boolean;
  /** Phone widths: state and version move under the name, columns collapse. */
  compact: boolean;
  /** Only offered while an update run is possible and one is available. */
  onUpdate?: () => void;
  onSettings?: () => void;
  onToggle: (on: boolean) => void;
}

export const AddonRow: React.FC<AddonRowProps> = ({
  entry,
  checked,
  disabled,
  compact,
  onUpdate,
  onSettings,
  onToggle,
}) => {
  const { t, i18n } = useTranslation('admin');

  // Backend before locale, for both name and description: that is what makes
  // an addon the backend knows but this WebUI release does not appear as
  // itself rather than as a raw translation key.
  const name =
    pickText(entry.name, i18n.language) ??
    t(`system.component_${entry.id}` as never);
  const summary =
    pickText(entry.summary, i18n.language) ??
    t(`system.component_${entry.id}_hint` as never);
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

  const state = (
    <Chip size="small" variant="outlined" color={stateColor()} label={stateLabel()} />
  );

  /**
   * What is on the box, or - for an addon that is not installed - what adding
   * it would bring. An addon that lives in a setting has neither: it is part
   * of the backend image and has no version of its own, which the dash says
   * more honestly than an empty cell.
   */
  const version = (): React.ReactNode => {
    if (isSettingAddon(entry)) {
      return (
        <Tooltip title={t('addons.version_builtin_hint')}>
          <Typography variant="body2" color="text.secondary">
            {t('addons.version_builtin')}
          </Typography>
        </Tooltip>
      );
    }
    const shown = entry.installed ? entry.version : entry.latest;
    if (!shown) return null;
    return (
      <Stack direction="row" spacing={0.5} alignItems="center" flexWrap="wrap">
        <Typography variant="body2" color="text.secondary">
          {shown}
        </Typography>
        {entry.update_available && entry.latest && (
          <Chip
            size="small"
            color="info"
            variant="outlined"
            label={t('addons.update_to', { version: entry.latest })}
          />
        )}
      </Stack>
    );
  };

  const actions = (
    <Stack direction="row" spacing={0.5} justifyContent="flex-end" alignItems="center">
      {entry.update_available && onUpdate && (
        <ActionButton
          actionType="icon"
          onClick={onUpdate}
          disabled={disabled}
          aria-label={t('addons.update_action', { name })}
        >
          <SystemUpdateAltIcon fontSize="small" />
        </ActionButton>
      )}
      {onSettings && (
        <ActionButton
          actionType="icon"
          onClick={onSettings}
          aria-label={t('addons.settings_action', { name })}
        >
          <SettingsIcon fontSize="small" />
        </ActionButton>
      )}
      <Switch
        checked={checked}
        onChange={(_, on) => onToggle(on)}
        disabled={disabled}
        color="primary"
        inputProps={{ 'aria-label': name }}
      />
    </Stack>
  );

  return (
    <TableRow>
      <TableCell sx={{ verticalAlign: 'top' }}>
        <Typography variant="body2" fontWeight={600}>
          {name}
        </Typography>
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
        {/* On a phone the two middle columns would leave the name about 40% of
            a 360px screen. They move under the description instead, where they
            read as the same two facts in the same order. */}
        {compact && (
          <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', flexWrap: 'wrap', mt: 0.5 }}>
            {state}
            {version()}
          </Box>
        )}
      </TableCell>
      {!compact && <TableCell sx={{ verticalAlign: 'top' }}>{state}</TableCell>}
      {!compact && <TableCell sx={{ verticalAlign: 'top' }}>{version()}</TableCell>}
      <TableCell align="right" sx={{ verticalAlign: 'top' }}>
        {actions}
      </TableCell>
    </TableRow>
  );
};
