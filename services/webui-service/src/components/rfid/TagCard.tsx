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
import { useTranslation } from 'react-i18next';
import type { Tag } from '@/types/api';

interface TagCardProps {
  tag: Tag;
  contentName?: string | null;
  onEdit: (tag: Tag) => void;
  onDelete: (tag: Tag) => void;
}

export const TagCard: React.FC<TagCardProps> = ({ tag, contentName, onEdit, onDelete }) => {
  const { t } = useTranslation('rfid');

  return (
    <Card variant="outlined" sx={{ borderRadius: 2 }}>
      <CardContent>
        <Box display="flex" alignItems="flex-start" justifyContent="space-between" gap={1}>
          <Box flex={1} minWidth={0}>
            <Typography variant="subtitle1" fontWeight={600} display="flex" alignItems="center" gap={1}>
              <NfcIcon fontSize="small" color="primary" />
              {tag.name ?? tag.tag_id}
            </Typography>
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
              {t('fields.tag_id')}: {tag.tag_id}
            </Typography>
            {contentName && (
              <Chip
                label={`${tag.content_type === 'playlist' ? '▶' : '♪'} ${contentName}`}
                size="small"
                color="primary"
                variant="outlined"
                sx={{ mt: 1 }}
              />
            )}
            {!contentName && (
              <Typography variant="caption" color="text.secondary">
                {t('fields.content')}: #{tag.content_id} ({tag.content_type})
              </Typography>
            )}
          </Box>
          <Box display="flex" alignItems="center" sx={{ mt: -0.5, mr: -0.5 }}>
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
