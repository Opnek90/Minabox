import React from 'react';
import { Box, Breadcrumbs, Chip, Link, Typography } from '@mui/material';
import FolderIcon from '@mui/icons-material/Folder';
import FolderOpenIcon from '@mui/icons-material/FolderOpen';
import HomeIcon from '@mui/icons-material/Home';
import { useTranslation } from 'react-i18next';
import type { TrackFolder } from '@/types/api';

interface FolderBreadcrumbProps {
  folders: TrackFolder[];
  currentFolderId: number | null;
  onNavigate: (folderId: number | null) => void;
}

/**
 * Builds the ancestor chain from root to currentFolderId.
 */
function buildPath(folders: TrackFolder[], currentId: number | null): TrackFolder[] {
  if (currentId === null) return [];
  const map = new Map(folders.map((f) => [f.id, f]));
  const path: TrackFolder[] = [];
  let node = map.get(currentId);
  while (node) {
    path.unshift(node);
    node = node.parent_id != null ? map.get(node.parent_id) : undefined;
  }
  return path;
}

export const FolderBreadcrumb: React.FC<FolderBreadcrumbProps> = ({
  folders,
  currentFolderId,
  onNavigate,
}) => {
  const { t } = useTranslation('media');
  const path = buildPath(folders, currentFolderId);

  if (currentFolderId === null) return null;

  return (
    <Box mb={1.5}>
      <Breadcrumbs aria-label="folder navigation" sx={{ fontSize: '0.85rem' }}>
        <Link
          component="button"
          underline="hover"
          color="inherit"
          onClick={() => onNavigate(null)}
          sx={{ display: 'flex', alignItems: 'center', gap: 0.5, cursor: 'pointer' }}
        >
          <HomeIcon sx={{ fontSize: 16 }} />
          {t('folders.root', { defaultValue: 'Library' })}
        </Link>
        {path.slice(0, -1).map((f) => (
          <Link
            key={f.id}
            component="button"
            underline="hover"
            color="inherit"
            onClick={() => onNavigate(f.id)}
            sx={{ display: 'flex', alignItems: 'center', gap: 0.5, cursor: 'pointer' }}
          >
            <FolderIcon sx={{ fontSize: 16 }} />
            {f.name}
          </Link>
        ))}
        <Chip
          icon={<FolderOpenIcon sx={{ fontSize: 16 }} />}
          label={
            <Typography variant="caption" fontWeight={600}>
              {path[path.length - 1]?.name}
            </Typography>
          }
          size="small"
          color="primary"
          variant="outlined"
        />
      </Breadcrumbs>
    </Box>
  );
};
