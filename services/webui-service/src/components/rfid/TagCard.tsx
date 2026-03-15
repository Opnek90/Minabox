import React from 'react';
import {
  Box,
  Card,
  CardContent,
  Chip,
  IconButton,
  Tooltip,
  Typography,
} from '@mui/material';
import EditIcon from '@mui/icons-material/Edit';
import DeleteIcon from '@mui/icons-material/Delete';
import NfcIcon from '@mui/icons-material/Nfc';
import AccessTimeIcon from '@mui/icons-material/AccessTime';
import BlockIcon from '@mui/icons-material/Block';
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline';
import { useTranslation } from 'react-i18next';
import type { Tag } from '@/types/api';

interface TagCardProps {
  tag: Tag;
  contentName?: string | null;
  onEdit: (tag: Tag) => void;
  onDelete: (tag: Tag) => void;
  onToggleDisabled: (tag: Tag) => void;
}

function formatRelativeTime(isoString: string | null, locale: string): string | null {
  if (!isoString) return null;
  try {
    const diff = Date.now() - new Date(isoString).getTime();
    const rtf = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' });
    const units: [Intl.RelativeTimeFormatUnit, number][] = [
      ['minute', 60_000],
      ['hour', 3_600_000],
      ['day', 86_400_000],
      ['week', 604_800_000],
    ];
    for (let i = units.length - 1; i >= 0; i--) {
      const [unit, ms] = units[i];
      if (diff >= ms) return rtf.format(-Math.round(diff / ms), unit);
    }
    return rtf.format(-Math.round(diff / 60_000), 'minute');
  } catch {
    return null;
  }
}

export const TagCard: React.FC<TagCardProps> = ({ tag, contentName, onEdit, onDelete, onToggleDisabled }) => {
  const { t, i18n } = useTranslation('rfid');
  const relativeTime = formatRelativeTime(tag.last_scanned_at, i18n.language);
  const isDisabled = tag.disabled ?? false;

  return (
    <Card
      variant="outlined"
      sx={{
        borderRadius: 2,
        opacity: isDisabled ? 0.65 : 1,
        borderColor: isDisabled ? 'text.disabled' : undefined,
      }}
    >
      <CardContent>
        <Box display="flex" alignItems="flex-start" justifyContent="space-between" gap={1}>
          <Box flex={1} minWidth={0}>
            <Typography variant="subtitle1" fontWeight={600} display="flex" alignItems="center" gap={1}>
              <NfcIcon fontSize="small" color={isDisabled ? 'disabled' : 'primary'} />
              {tag.name ?? tag.tag_id}
            </Typography>
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
              {t('fields.tag_id')}: {tag.tag_id}
            </Typography>

            {isDisabled && (
              <Chip
                label={t('tag_disabled_label', { defaultValue: 'Gesperrt' })}
                size="small"
                color="default"
                variant="outlined"
                icon={<BlockIcon />}
                sx={{ mt: 1, mr: 1 }}
              />
            )}

            {contentName && (
              <Chip
                label={`${tag.content_type === 'playlist' ? '▶' : '♪'} ${contentName}`}
                size="small"
                color={isDisabled ? 'default' : 'primary'}
                variant="outlined"
                sx={{ mt: 1 }}
              />
            )}
            {!contentName && (
              <Typography variant="caption" color="text.secondary">
                {t('fields.content')}: #{tag.content_id} ({tag.content_type})
              </Typography>
            )}
            {relativeTime && (
              <Box display="flex" alignItems="center" gap={0.5} mt={0.75}>
                <AccessTimeIcon sx={{ fontSize: 12, color: 'text.disabled' }} />
                <Typography variant="caption" color="text.disabled">
                  {t('fields.last_scanned')}: {relativeTime}
                </Typography>
              </Box>
            )}
          </Box>
          <Box display="flex" alignItems="center" sx={{ mt: -0.5, mr: -0.5 }}>
            <Tooltip title={isDisabled
              ? t('enable_tag', { defaultValue: 'Tag freischalten' })
              : t('disable_tag', { defaultValue: 'Tag sperren' })
            }>
              <IconButton
                size="small"
                color={isDisabled ? 'success' : 'warning'}
                onClick={() => onToggleDisabled(tag)}
              >
                {isDisabled ? <CheckCircleOutlineIcon fontSize="small" /> : <BlockIcon fontSize="small" />}
              </IconButton>
            </Tooltip>
            <Tooltip title={t('edit_tag')}>
              <IconButton size="small" onClick={() => onEdit(tag)}>
                <EditIcon fontSize="small" />
              </IconButton>
            </Tooltip>
            <Tooltip title={t('delete_tag')}>
              <IconButton size="small" color="error" onClick={() => onDelete(tag)}>
                <DeleteIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          </Box>
        </Box>
      </CardContent>
    </Card>
  );
};
