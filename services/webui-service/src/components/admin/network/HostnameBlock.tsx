import React, { useCallback, useEffect, useState } from 'react';
import {
  Box,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  TextField,
  Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import { useToast } from '@/contexts/ToastContext';
import { systemApi } from '@/api/system';
import { ActionButton } from '@/components/ui/ActionButton';
import { SettingsBlock } from '@/components/admin/SettingsBlock';
import { translateApiError } from '@/utils/apiError';

/** Der Name, unter dem die Box im Netz auftaucht - und damit auch ihre mDNS-Adresse. */
export const HostnameBlock: React.FC = () => {
  const { t, i18n } = useTranslation('admin');
  const { showSuccess, showError } = useToast();

  const [hostname, setHostname] = useState<string | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [draft, setDraft] = useState('');
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await systemApi.getHostname();
      setHostname(res?.hostname ?? null);
    } catch {
      setHostname(null);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const handleApply = async () => {
    const name = draft.trim().toLowerCase();
    if (!name) return;
    setSaving(true);
    try {
      await systemApi.setHostname(name);
      await load();
      setDialogOpen(false);
      showSuccess(t('system.hostname_apply'));
    } catch (err) {
      showError(translateApiError(t, i18n, err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <SettingsBlock title={t('system.host_hostname')}>
      <Box display="flex" flexWrap="wrap" gap={1} alignItems="center">
        {hostname != null && (
          <Typography variant="body2" color="text.secondary">{hostname}</Typography>
        )}
        <ActionButton
          actionType="secondary"
          onClick={() => { setDraft(hostname ?? ''); setDialogOpen(true); }}
          disabled={saving}
        >
          {t('system.hostname_edit')}
        </ActionButton>
      </Box>

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)}>
        <DialogTitle>{t('system.hostname_dialog_title')}</DialogTitle>
        <DialogContent>
          <DialogContentText sx={{ mb: 1 }}>
            {t('system.hostname_reconnect_hint')}
          </DialogContentText>
          <TextField
            autoFocus
            fullWidth
            margin="dense"
            label={t('system.host_hostname')}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="minabox"
            inputProps={{ maxLength: 63 }}
          />
        </DialogContent>
        <DialogActions>
          <ActionButton actionType="secondary" onClick={() => setDialogOpen(false)}>
            {t('actions.cancel', { ns: 'common' })}
          </ActionButton>
          <ActionButton
            actionType="primary"
            onClick={handleApply}
            disabled={saving || !draft.trim()}
            loading={saving}
          >
            {t('system.hostname_apply')}
          </ActionButton>
        </DialogActions>
      </Dialog>
    </SettingsBlock>
  );
};
