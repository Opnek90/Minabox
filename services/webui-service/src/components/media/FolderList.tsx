import React from 'react';
import { Grid } from '@mui/material';
import { FolderCard } from './FolderCard';
import type { Track, TrackFolder } from '@/types/api';

interface FolderListProps {
  folders: TrackFolder[];
  currentFolderId: number | null;
  allTracks: Track[];
  onNavigate: (folderId: number) => void;
  onRename: (folder: TrackFolder) => void;
  onDelete: (folder: TrackFolder) => void;
}

export const FolderList: React.FC<FolderListProps> = ({
  folders,
  currentFolderId,
  allTracks,
  onNavigate,
  onRename,
  onDelete,
}) => {
  const children = folders.filter((f) => f.parent_id === currentFolderId);

  if (children.length === 0) return null;

  return (
    <Grid container spacing={1.5} mb={2}>
      {children.map((folder) => {
        const trackCount = allTracks.filter((t) => t.folder_id === folder.id).length;
        const subfolderCount = folders.filter((f) => f.parent_id === folder.id).length;
        return (
          <Grid item xs={12} sm={6} md={4} lg={3} key={folder.id}>
            <FolderCard
              folder={folder}
              trackCount={trackCount}
              subfolderCount={subfolderCount}
              onClick={() => onNavigate(folder.id)}
              onRename={() => onRename(folder)}
              onDelete={() => onDelete(folder)}
            />
          </Grid>
        );
      })}
    </Grid>
  );
};
