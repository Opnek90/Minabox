import React, { useCallback, useEffect, useState } from 'react';
import {
  Box,
  FormControlLabel,
  Radio,
  RadioGroup,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import SaveIcon from '@mui/icons-material/Save';
import { useTranslation } from 'react-i18next';
import { useToast } from '@/contexts/ToastContext';
import { systemApi, type NetworkResponse } from '@/api/system';
import { ActionButton } from '@/components/ui/ActionButton';
import { SettingsBlock } from '@/components/admin/SettingsBlock';
import { translateApiError } from '@/utils/apiError';

type Method = 'dhcp' | 'manual';

interface Draft {
  method: Method;
  address: string;
  netmask: string;
  gateway: string;
  dns: string;
}

const DEFAULT_NETMASK = '24';

function toDraft(net: NetworkResponse): Draft {
  return {
    method: net.method,
    address: net.address ?? '',
    netmask: net.netmask ?? DEFAULT_NETMASK,
    gateway: net.gateway ?? '',
    dns: net.dns ?? '',
  };
}

interface IPv4BlockProps {
  /** Nach dem Uebernehmen, damit die Status-Karte die neue Adresse zeigt. */
  onNetworkChanged: () => void;
}

/** Feste IP-Adresse statt DHCP - fuer Boxen, die immer unter derselben Adresse stehen sollen. */
export const IPv4Block: React.FC<IPv4BlockProps> = ({ onNetworkChanged }) => {
  const { t, i18n } = useTranslation('admin');
  const { showSuccess, showError } = useToast();

  const [network, setNetwork] = useState<NetworkResponse | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      const net = await systemApi.getNetwork();
      setNetwork(net);
      setDraft(net ? toDraft(net) : null);
    } catch {
      setNetwork(null);
      setDraft(null);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const set = <K extends keyof Draft>(key: K, value: Draft[K]) =>
    setDraft((prev) => (prev ? { ...prev, [key]: value } : prev));

  const handleMethodChange = (method: Method) => {
    // Beim Wechsel auf "manuell" die zuletzt bekannten Werte vorlegen, statt
    // vier leere Felder hinzustellen.
    setDraft((prev) => {
      if (!prev) return prev;
      if (method === 'manual' && network) return { ...toDraft(network), method };
      return { ...prev, method };
    });
  };

  const handleApply = async () => {
    if (!draft) return;
    const manual = draft.method === 'manual';
    setSaving(true);
    try {
      await systemApi.setNetwork({
        method: draft.method,
        address: manual ? draft.address.trim() || undefined : undefined,
        netmask: manual ? draft.netmask.trim() || undefined : undefined,
        gateway: manual ? draft.gateway.trim() || undefined : undefined,
        dns: manual ? draft.dns.trim() || undefined : undefined,
      });
      await load();
      showSuccess(t('system.network_apply'));
      onNetworkChanged();
    } catch (err) {
      showError(translateApiError(t, i18n, err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <SettingsBlock title={t('system.network_title')}>
      {draft === null ? (
        <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
          {t('system.network_no_connection')}
        </Typography>
      ) : (
        <Box display="flex" flexDirection="column" gap={1.5} sx={{ mt: 1 }}>
          <Typography variant="caption" color="text.secondary">
            {t('system.network_method_label')}
          </Typography>
          <RadioGroup
            row
            value={draft.method}
            onChange={(_, v) => handleMethodChange(v as Method)}
          >
            <FormControlLabel
              value="dhcp"
              control={<Radio size="small" />}
              label={t('system.network_method_dhcp')}
            />
            <FormControlLabel
              value="manual"
              control={<Radio size="small" />}
              label={t('system.network_method_manual')}
            />
          </RadioGroup>

          {draft.method === 'manual' && (
            <Stack direction="row" flexWrap="wrap" gap={1} alignItems="center" sx={{ mt: 0.5 }}>
              <TextField size="small" label={t('system.network_address')} value={draft.address}
                onChange={(e) => set('address', e.target.value)} placeholder="192.168.1.10" sx={{ minWidth: 140 }} />
              <TextField size="small" label={t('system.network_netmask')} value={draft.netmask}
                onChange={(e) => set('netmask', e.target.value)} placeholder="24" sx={{ width: 72 }} />
              <TextField size="small" label={t('system.network_gateway')} value={draft.gateway}
                onChange={(e) => set('gateway', e.target.value)} placeholder="192.168.1.1" sx={{ minWidth: 120 }} />
              <TextField size="small" label={t('system.network_dns')} value={draft.dns}
                onChange={(e) => set('dns', e.target.value)} placeholder="192.168.1.1" sx={{ minWidth: 120 }} />
            </Stack>
          )}

          <Box display="flex" flexWrap="wrap" gap={1}>
            <ActionButton
              actionType="primary"
              startIcon={<SaveIcon />}
              onClick={handleApply}
              disabled={saving}
              loading={saving}
            >
              {t('system.network_apply')}
            </ActionButton>
          </Box>
        </Box>
      )}
    </SettingsBlock>
  );
};
