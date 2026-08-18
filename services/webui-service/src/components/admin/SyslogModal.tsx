import React, { useCallback, useEffect, useState } from 'react';
import {
  Box,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Typography,
} from '@mui/material';
import RefreshIcon from '@mui/icons-material/Refresh';
import { useTranslation } from 'react-i18next';
import { systemApi } from '@/api/system';
import { ActionButton } from '@/components/ui/ActionButton';
import { ResponsiveDialog } from '@/components/common/ResponsiveDialog';

interface SyslogModalProps {
  open: boolean;
  onClose: () => void;
}

export const SyslogModal: React.FC<SyslogModalProps> = ({ open, onClose }) => {
  const { t } = useTranslation('admin');
  const [source, setSource] = useState<'kernel' | 'docker'>('kernel');
  const [lines, setLines] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!open) return;
    setLoading(true);
    setError(null);
    try {
      const data = await systemApi.getSyslog(200, source);
      setLines(data.lines ?? []);
    } catch {
      setError(t('system.syslog_unavailable'));
      setLines([]);
    } finally {
      setLoading(false);
    }
  }, [open, source, t]);

  useEffect(() => {
    if (open) load();
  }, [open, load]);

  return (
    <ResponsiveDialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>{t('system.syslog')}</DialogTitle>
      <DialogContent>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 1 }}>
          <FormControl size="small" sx={{ minWidth: 140 }}>
            <InputLabel>{t('system.syslog')}</InputLabel>
            <Select
              value={source}
              label={t('system.syslog')}
              onChange={(e) => setSource(e.target.value as 'kernel' | 'docker')}
            >
              <MenuItem value="kernel">{t('system.syslog_kernel')}</MenuItem>
              <MenuItem value="docker">{t('system.syslog_docker')}</MenuItem>
            </Select>
          </FormControl>
          <ActionButton
            actionType="secondary"
            size="small"
            startIcon={<RefreshIcon />}
            onClick={load}
            disabled={loading}
          >
            {t('system.view_logs')}
          </ActionButton>
        </Box>
        {error && (
          <Typography color="error" variant="body2" sx={{ mb: 1 }}>
            {error}
          </Typography>
        )}
        <Box
          component="pre"
          sx={{
            bgcolor: 'action.hover',
            p: 1.5,
            borderRadius: 1,
            overflow: 'auto',
            maxHeight: 400,
            fontSize: '0.75rem',
            fontFamily: 'monospace',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-all',
          }}
        >
          {loading ? '…' : lines.length === 0 ? (error ? '' : '—') : lines.join('\n')}
        </Box>
      </DialogContent>
      <DialogActions>
        <ActionButton actionType="secondary" onClick={onClose}>
          {t('actions.close', { ns: 'common' })}
        </ActionButton>
      </DialogActions>
    </ResponsiveDialog>
  );
};
