import React from 'react';
import {
  Alert,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import { pickText, type AddonEntry } from '@/api/addons';
import { ADDON_SETTINGS_CONTENT } from '@/config/addonSettings';
import { ActionButton } from '@/components/ui/ActionButton';
import { useLayout } from '@/hooks/useLayout';

/**
 * Everything about one addon, behind the gear button of its row.
 *
 * The panel it shows is the same component the settings page renders in its
 * own section - one source, two ways in (`@/config/addonSettings`). That is
 * deliberate: announcements are found under "Sound" by anyone looking for a
 * volume, and the addons page is where you go when you are thinking about the
 * addon itself. Neither reading is wrong, and nothing is duplicated for it.
 *
 * An addon this WebUI release has no panel for still opens: it shows what the
 * catalogue says about it. That is the case that makes a new addon usable
 * without a new WebUI - it arrives described, if not yet configurable.
 */
interface AddonSettingsDialogProps {
  entry: AddonEntry | null;
  onClose: () => void;
}

export const AddonSettingsDialog: React.FC<AddonSettingsDialogProps> = ({
  entry,
  onClose,
}) => {
  const { t, i18n } = useTranslation(['admin', 'common']);
  const { isMobile } = useLayout();

  if (!entry) return null;

  const name =
    pickText(entry.name, i18n.language) ??
    t(`system.component_${entry.id}` as never);
  const summary = pickText(entry.summary, i18n.language);
  const content = entry.settings_section
    ? ADDON_SETTINGS_CONTENT[entry.settings_section]
    : undefined;

  return (
    <Dialog
      open
      onClose={onClose}
      maxWidth="sm"
      fullWidth
      fullScreen={isMobile}
      aria-labelledby="addon-settings-title"
    >
      <DialogTitle id="addon-settings-title">{name}</DialogTitle>
      <DialogContent dividers>
        {summary && (
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            {summary}
          </Typography>
        )}
        {content ?? (
          <Alert severity="info">{t('addons.no_settings')}</Alert>
        )}
      </DialogContent>
      <DialogActions>
        <ActionButton actionType="secondary" onClick={onClose}>
          {t('actions.close', { ns: 'common' })}
        </ActionButton>
      </DialogActions>
    </Dialog>
  );
};
