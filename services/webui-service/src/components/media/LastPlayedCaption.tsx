import React from 'react';
import { Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { formatAbsoluteTime, formatRelativeTime } from '@/utils/formatTime';

interface LastPlayedCaptionProps {
  /** Backend timestamp (naive UTC), e.g. `track.last_played_at`. */
  value: string | null | undefined;
  /** Translated label, default: "Last played". */
  label?: string;
  /** A leading "·" when the value follows other captions on one line. */
  separator?: boolean;
  /**
   * Text for "never played". Without this value the line stays empty - so e.g.
   * "last fetched" can still be omitted entirely. Deliberately not italic:
   * no italic face is loaded, the browser would only slant the glyphs.
   */
  emptyLabel?: string;
}

/**
 * A uniform "last played" display for tracks, streams and podcasts.
 *
 * Every list used to compute this itself and each in a fixed unit - podcasts in
 * minutes ("203,844 minutes ago"), streams in hours, tracks not at all. The
 * unit is now chosen by {@link formatRelativeTime}; the exact date is in the
 * tooltip.
 */
export const LastPlayedCaption: React.FC<LastPlayedCaptionProps> = ({
  value,
  label,
  separator = false,
  emptyLabel,
}) => {
  const { t, i18n } = useTranslation('media');
  const relative = formatRelativeTime(value, i18n.language);

  if (!relative && !emptyLabel) return null;

  const caption = label ?? t('tracks.fields.last_played');
  const absolute = relative ? formatAbsoluteTime(value, i18n.language) : null;

  return (
    <Typography
      component="span"
      variant="caption"
      // text.secondary statt text.disabled: das blasse Disabled-Grau (38 %
      // Deckkraft) ist im hellen Theme kaum noch zu lesen.
      color="text.secondary"
      sx={{ flexShrink: 0 }}
      title={absolute ? `${caption}: ${absolute}` : undefined}
    >
      {separator ? '· ' : ''}
      {relative ? `${caption}: ${relative}` : emptyLabel}
    </Typography>
  );
};
