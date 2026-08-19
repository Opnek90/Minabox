import React from 'react';
import { Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { formatAbsoluteTime, formatRelativeTime } from '@/utils/formatTime';

interface LastPlayedCaptionProps {
  /** Backend-Zeitstempel (naive UTC), z. B. `track.last_played_at`. */
  value: string | null | undefined;
  /** Uebersetzter Bezeichner, Default: "Zuletzt gespielt". */
  label?: string;
  /** Fuehrendes "·", wenn die Angabe hinter anderen Captions in einer Zeile steht. */
  separator?: boolean;
  /**
   * Text fuer "noch nie gespielt". Ohne diesen Wert bleibt die Zeile leer –
   * so kann etwa "zuletzt abgerufen" weiterhin ganz entfallen. Bewusst nicht
   * kursiv ausgezeichnet: es ist kein Kursiv-Schnitt geladen, der Browser
   * wuerde die Glyphen nur schraegstellen.
   */
  emptyLabel?: string;
}

/**
 * Einheitliche "zuletzt gespielt"-Anzeige fuer Tracks, Streams und Podcasts.
 *
 * Vorher rechnete jede Liste selbst und jeweils in einer festen Einheit –
 * Podcasts in Minuten ("vor 203.844 Minuten"), Streams in Stunden, Tracks gar
 * nicht. Die Einheit waehlt jetzt {@link formatRelativeTime}; das genaue Datum
 * steht im Tooltip.
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
