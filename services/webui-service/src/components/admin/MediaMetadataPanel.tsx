import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Box, LinearProgress, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { useToast } from '@/contexts/ToastContext';
import { tracksApi } from '@/api/tracks';
import { translateApiError } from '@/utils/apiError';
import { ActionButton } from '@/components/ui/ActionButton';
import { SettingsBlock } from '@/components/admin/SettingsBlock';
import type { MetadataBackfillStatus } from '@/types/api';

/**
 * The one-off action that fills artist/album/cover for tracks imported before
 * online metadata was switched on.
 *
 * Whether the box may ask MusicBrainz at all used to be a switch right above
 * this - it is the addon itself now, and lives as a row in the addons table
 * (`components/admin/addons`). Keeping a second copy of it here would have
 * meant two switches for one setting on two pages.
 */
export const MediaMetadataPanel: React.FC = () => {
  const { t, i18n } = useTranslation('admin');
  const { showError, showSuccess } = useToast();

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
