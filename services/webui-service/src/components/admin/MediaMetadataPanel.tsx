import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Box, FormControlLabel, LinearProgress, Switch, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { useToast } from '@/contexts/ToastContext';
import { useGeneralConfigField } from '@/hooks/useGeneralConfig';
import { tracksApi } from '@/api/tracks';
import { translateApiError } from '@/utils/apiError';
import { ActionButton } from '@/components/ui/ActionButton';
import { SettingsBlock } from '@/components/admin/SettingsBlock';
import type { MetadataBackfillStatus } from '@/types/api';
import { HelpLabel } from '@/components/ui/HelpTip';

/**
 * Two things that belong together: whether the box may ask MusicBrainz for
 * artist/album/cover, and a one-off action that fills those fields for tracks
 * that were imported before this feature existed.
 */
export const MediaMetadataPanel: React.FC = () => {
  const { t, i18n } = useTranslation('admin');
  const { showError, showSuccess } = useToast();

  const {
    value: onlineEnabled,
    setValue: setOnlineEnabled,
    save: saveOnlineEnabled,
  } = useGeneralConfigField('online_metadata_lookup_enabled', false);

  const [status, setStatus] = useState<MetadataBackfillStatus | null>(null);
  const [starting, setStarting] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollRef.current !== null) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const poll = useCallback(async () => {
    try {
      const next = await tracksApi.getBackfillStatus();
      setStatus(next);
      if (!next.running) {
        stopPolling();
        if (next.error) showError(t('general.metadata_backfill_error'));
        else showSuccess(t('general.metadata_backfill_done', { count: next.updated }));
      }
    } catch {
      stopPolling();
    }
  }, [showError, showSuccess, stopPolling, t]);

  useEffect(() => {
    // A run started from another tab (or still going from a previous visit)
    // should show up here too.
    void poll();
    return stopPolling;
    // poll/stopPolling are stable
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (status?.running && pollRef.current === null) {
      pollRef.current = setInterval(() => void poll(), 2000);
    }
  }, [status?.running, poll]);

  const handleOnlineToggle = async (checked: boolean) => {
    setOnlineEnabled(checked);
    try {
      await saveOnlineEnabled();
    } catch (err) {
      setOnlineEnabled(!checked);
      showError(translateApiError(t, i18n, err));
    }
  };

  const handleBackfill = async () => {
    setStarting(true);
    try {
      await tracksApi.backfillMetadata();
      setStatus(await tracksApi.getBackfillStatus());
    } catch (err) {
      showError(translateApiError(t, i18n, err));
    } finally {
      setStarting(false);
    }
  };

  const running = status?.running ?? false;

  return (
    <Box display="flex" flexDirection="column" gap={2}>
      <SettingsBlock title={t('general.online_metadata_title')}>
        <FormControlLabel
          control={
            <Switch
              checked={onlineEnabled ?? false}
              onChange={(_, checked) => void handleOnlineToggle(checked)}
              color="primary"
            />
          }
          label={
            <HelpLabel
              text={t('general.online_metadata_label')}
              help={t('general.online_metadata_hint')}
            />
          }
          sx={{ display: 'block' }}
        />
      </SettingsBlock>

      <SettingsBlock
        title={t('general.metadata_backfill_title')}
        help={t('general.metadata_backfill_hint')}
      >
        <ActionButton
          actionType="primary"
          onClick={handleBackfill}
          disabled={starting || running}
          loading={starting}
        >
          {t('general.metadata_backfill_start')}
        </ActionButton>
        {running && status && (
          <Box sx={{ mt: 1.5 }}>
            <LinearProgress
              variant={status.total > 0 ? 'determinate' : 'indeterminate'}
              value={status.total > 0 ? (status.processed / status.total) * 100 : undefined}
              sx={{ borderRadius: 1 }}
            />
            <Typography variant="caption" color="text.secondary">
              {t('general.metadata_backfill_progress', {
                processed: status.processed,
                total: status.total,
                updated: status.updated,
              })}
            </Typography>
          </Box>
        )}
      </SettingsBlock>
    </Box>
  );
};
