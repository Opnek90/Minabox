import React from 'react';
import { Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { formatAbsoluteTime, formatRelativeTime } from '@/utils/formatTime';

interface RelativeTimeCellProps {
  /** Backend timestamp (naive UTC), e.g. `track.last_played_at`. */
  value: string | null | undefined;
  /** Shown when there is no timestamp. */
  emptyLabel?: string;
}

/**
 * Compact "x days ago" cell for the details view, with the exact date in the
 * tooltip. Mirrors {@link LastPlayedCaption} but without the leading label,
 * because the column header already names the field.
 */
export const RelativeTimeCell: React.FC<RelativeTimeCellProps> = ({ value, emptyLabel = '—' }) => {
  const { i18n } = useTranslation();
  const relative = formatRelativeTime(value, i18n.language);

  if (!relative) {
    return (
      <Typography component="span" variant="body2" color="text.secondary">
        {emptyLabel}
      </Typography>
    );
  }

  return (
    <Typography
      component="span"
      variant="body2"
      title={formatAbsoluteTime(value, i18n.language) ?? undefined}
    >
      {relative}
    </Typography>
  );
};
