import React, { useState } from 'react';
import {
  Box,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  FormControlLabel,
  TextField,
  Typography,
} from '@mui/material';
import ComputerIcon from '@mui/icons-material/Computer';
import PowerSettingsNewIcon from '@mui/icons-material/PowerSettingsNew';
import RestartAltIcon from '@mui/icons-material/RestartAlt';
import RestoreIcon from '@mui/icons-material/Restore';
import { useTranslation } from 'react-i18next';
import { useToast } from '@/contexts/ToastContext';
import { systemApi } from '@/api/system';
import { ActionButton } from '@/components/ui/ActionButton';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { SettingsBlock } from '@/components/admin/SettingsBlock';
import { translateApiError } from '@/utils/apiError';

type Ask = 'restart' | 'reboot' | 'shutdown' | null;

/**
 * Everything that interrupts or ends operation.
 *
 * Two fixed rows instead of one wrapping block: on top what only interrupts,
 * below what ends or deletes. With width-based wrapping, "Shut down" would
 * otherwise land next to the harmless restarts.
 */
export const PowerBlock: React.FC = () => {
  const { t, i18n } = useTranslation('admin');
  const { showSuccess, showError } = useToast();
  const [ask, setAsk] = useState<Ask>(null);
  const [resetOpen, setResetOpen] = useState(false);
  const [resetDeleteAudio, setResetDeleteAudio] = useState(false);
  const [resetConfirmText, setResetConfirmText] = useState('');
  const [resetPending, setResetPending] = useState(false);

  // The three restart variants all cut the connection the response would come
  // back over - an error from that is not an error, it is the success.
  const POWER_ACTIONS: Record<Exclude<Ask, null>, { titleKey: string; messageKey: string; run: () => Promise<void> }> = {
    restart: { titleKey: 'system.restart', messageKey: 'system.restart_confirm', run: systemApi.restart },
    reboot: { titleKey: 'system.reboot', messageKey: 'system.reboot_confirm', run: systemApi.rebootHost },
    shutdown: { titleKey: 'system.shutdown', messageKey: 'system.shutdown_confirm', run: systemApi.shutdownHost },
  };

  const handleConfirmPower = async () => {
    if (!ask) return;
    const action = POWER_ACTIONS[ask];
    setAsk(null);
    try { await action.run(); } catch { /* die Verbindung geht dabei weg */ }
  };

  const confirmWord = t('system.factory_reset_confirm_word');
  const resetValid = resetConfirmText.trim() === confirmWord;

  const closeReset = () => {
    setResetOpen(false);
    setResetConfirmText('');
  };

  const handleFactoryReset = async () => {
    if (!resetValid) return;
    closeReset();
    setResetPending(true);
    try {
      await systemApi.factoryReset(resetDeleteAudio);
      showSuccess(t('system.factory_reset_success'));
    } catch (err) {
      showError(translateApiError(t, i18n, err));
    } finally {
      setResetPending(false);
    }
  };

  return (
    <SettingsBlock title={t('system.restart_group')}>
      <Box display="flex" flexWrap="wrap" gap={1}>
        <ActionButton actionType="secondary" startIcon={<RestartAltIcon />} onClick={() => setAsk('restart')}>
          {t('system.restart')}
        </ActionButton>
        <ActionButton actionType="secondary" startIcon={<ComputerIcon />} onClick={() => setAsk('reboot')}>
          {t('system.reboot')}
        </ActionButton>
      </Box>
      <Box display="flex" flexWrap="wrap" gap={1} sx={{ mt: 1 }}>
        <ActionButton actionType="destructive" startIcon={<PowerSettingsNewIcon />} onClick={() => setAsk('shutdown')}>
          {t('system.shutdown')}
        </ActionButton>
        <ActionButton
          actionType="destructive"
          startIcon={<RestoreIcon />}
          onClick={() => { setResetOpen(true); setResetConfirmText(''); }}
          disabled={resetPending}
        >
          {t('system.factory_reset')}
        </ActionButton>
      </Box>

      <ConfirmDialog
        open={ask !== null}
        title={ask ? t(POWER_ACTIONS[ask].titleKey) : ''}
        message={ask ? t(POWER_ACTIONS[ask].messageKey) : ''}
        destructive
        onCancel={() => setAsk(null)}
        onConfirm={handleConfirmPower}
      />

      {/* Eigener Dialog statt ConfirmDialog: hier muss zusaetzlich entschieden
          werden, ob die Musik mit weg soll, und das Wort getippt werden. */}
      <Dialog open={resetOpen} onClose={closeReset}>
        <DialogTitle>{t('system.factory_reset')}</DialogTitle>
        <DialogContent>
          <DialogContentText sx={{ mb: 2 }}>{t('system.factory_reset_warning')}</DialogContentText>
          <FormControlLabel
            control={
              <Checkbox
                checked={resetDeleteAudio}
                onChange={(_, c) => setResetDeleteAudio(c)}
                color="primary"
              />
            }
            label={t('system.factory_reset_delete_audio')}
            sx={{ display: 'block', mb: 2 }}
          />
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
            {t('system.factory_reset_type_prompt')}
          </Typography>
          <TextField
            fullWidth
            size="small"
            value={resetConfirmText}
            onChange={(e) => setResetConfirmText(e.target.value)}
            placeholder={confirmWord}
            autoComplete="off"
          />
        </DialogContent>
        <DialogActions>
          <ActionButton actionType="secondary" onClick={closeReset}>
            {t('actions.cancel', { ns: 'common' })}
          </ActionButton>
          <ActionButton
            actionType="destructive"
            onClick={handleFactoryReset}
            disabled={!resetValid || resetPending}
          >
            {t('actions.confirm', { ns: 'common' })}
          </ActionButton>
        </DialogActions>
      </Dialog>
    </SettingsBlock>
  );
};
