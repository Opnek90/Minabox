import React from 'react';
import {
  Box,
  Card,
  CardActionArea,
  IconButton,
  Menu,
  MenuItem,
  Tooltip,
  Typography,
} from '@mui/material';
import DeleteIcon from '@mui/icons-material/Delete';
import DriveFileRenameOutlineIcon from '@mui/icons-material/DriveFileRenameOutline';
import FolderIcon from '@mui/icons-material/Folder';
import MoreVertIcon from '@mui/icons-material/MoreVert';
import { useTranslation } from 'react-i18next';
import type { TrackFolder } from '@/types/api';

interface FolderCardProps {
  folder: TrackFolder;
  trackCount: number;
  subfolderCount: number;
  onClick: () => void;
  onRename: () => void;
  onDelete: () => void;
}

export const FolderCard: React.FC<FolderCardProps> = ({
  folder,
  trackCount,
  subfolderCount,
  onClick,
  onRename,
  onDelete,
}) => {
  const { t } = useTranslation('media');
  const [anchorEl, setAnchorEl] = React.useState<null | HTMLElement>(null);

  const handleMenuOpen = (e: React.MouseEvent<HTMLElement>) => {
    e.stopPropagation();
    setAnchorEl(e.currentTarget);
  };
  const handleMenuClose = () => setAnchorEl(null);

  const meta: string[] = [];
  if (trackCount > 0) meta.push(t('folders.track_count', { count: trackCount }));
  if (subfolderCount > 0) meta.push(t('folders.subfolder_count', { count: subfolderCount }));

  return (
    <Card
      variant="outlined"
      sx={{
        display: 'flex',
        alignItems: 'center',
        borderRadius: 2,
        position: 'relative',
        '&:hover': { borderColor: 'primary.main', bgcolor: 'action.hover' },
        transition: 'border-color 0.15s, background-color 0.15s',
      }}
    >
      <CardActionArea
        onClick={onClick}
        sx={{ display: 'flex', alignItems: 'center', p: 1.5, flex: 1, justifyContent: 'flex-start' }}
      >
        <FolderIcon color="primary" sx={{ fontSize: 36, mr: 1.5, flexShrink: 0 }} />
        <Box overflow="hidden">
          <Typography variant="subtitle2" fontWeight={600} noWrap>{folder.name}</Typography>
          {meta.length > 0 && (
            <Typography variant="caption" color="text.secondary" noWrap>{meta.join(' · ')}</Typography>
          )}
        </Box>
      </CardActionArea>

      <Tooltip title={t('folders.options')}>
        <IconButton size="small" onClick={handleMenuOpen} sx={{ mr: 0.5 }}>
          <MoreVertIcon fontSize="small" />
        </IconButton>
      </Tooltip>

      <Menu anchorEl={anchorEl} open={Boolean(anchorEl)} onClose={handleMenuClose}>
        <MenuItem onClick={() => { handleMenuClose(); onRename(); }}>
          <DriveFileRenameOutlineIcon fontSize="small" sx={{ mr: 1 }} />
          {t('folders.rename')}
        </MenuItem>
        <MenuItem onClick={() => { handleMenuClose(); onDelete(); }} sx={{ color: 'error.main' }}>
          <DeleteIcon fontSize="small" sx={{ mr: 1 }} />
          {t('folders.delete')}
        </MenuItem>
      </Menu>
    </Card>
  );
};
