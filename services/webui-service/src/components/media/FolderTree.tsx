import React, { useState } from 'react';
import {
  Box,
  Collapse,
  IconButton,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Menu,
  MenuItem,
  Tooltip,
  Typography,
} from '@mui/material';
import ChevronRightIcon from '@mui/icons-material/ChevronRight';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import FolderIcon from '@mui/icons-material/Folder';
import FolderOpenIcon from '@mui/icons-material/FolderOpen';
import LibraryMusicIcon from '@mui/icons-material/LibraryMusic';
import MoreVertIcon from '@mui/icons-material/MoreVert';
import { useTranslation } from 'react-i18next';
import type { Track, TrackFolder } from '@/types/api';

interface FolderTreeProps {
  folders: TrackFolder[];
  allTracks: Track[];
  currentFolderId: number | null;
  onNavigate: (folderId: number | null) => void;
  onRename: (folder: TrackFolder) => void;
  onDelete: (folder: TrackFolder) => void;
}

interface TreeNodeProps {
  folder: TrackFolder;
  folders: TrackFolder[];
  allTracks: Track[];
  currentFolderId: number | null;
  depth: number;
  onNavigate: (folderId: number | null) => void;
  onRename: (folder: TrackFolder) => void;
  onDelete: (folder: TrackFolder) => void;
}

const TreeNode: React.FC<TreeNodeProps> = ({
  folder, folders, allTracks, currentFolderId, depth,
  onNavigate, onRename, onDelete,
}) => {
  const children = folders.filter((f) => f.parent_id === folder.id);
  const hasChildren = children.length > 0;
  const isSelected = currentFolderId === folder.id;
  const trackCount = allTracks.filter((t) => t.folder_id === folder.id).length;

  const [expanded, setExpanded] = useState(true);
  const [menuAnchor, setMenuAnchor] = useState<HTMLElement | null>(null);

  return (
    <>
      <ListItemButton
        selected={isSelected}
        onClick={() => onNavigate(folder.id)}
        sx={{
          pl: 1 + depth * 2,
          pr: 0.5,
          py: 0.4,
          borderRadius: 1,
          mx: 0.5,
          '&.Mui-selected': { bgcolor: 'primary.main', color: 'primary.contrastText',
            '& .MuiListItemIcon-root': { color: 'primary.contrastText' },
            '&:hover': { bgcolor: 'primary.dark' },
          },
        }}
      >
        <ListItemIcon sx={{ minWidth: 24 }}>
          {hasChildren ? (
            <IconButton
              size="small"
              onClick={(e) => { e.stopPropagation(); setExpanded((v) => !v); }}
              sx={{ p: 0, color: 'inherit' }}
            >
              {expanded ? <ExpandMoreIcon sx={{ fontSize: 16 }} /> : <ChevronRightIcon sx={{ fontSize: 16 }} />}
            </IconButton>
          ) : (
            <Box sx={{ width: 24 }} />
          )}
        </ListItemIcon>
        <ListItemIcon sx={{ minWidth: 28 }}>
          {isSelected ? <FolderOpenIcon sx={{ fontSize: 18 }} /> : <FolderIcon sx={{ fontSize: 18 }} />}
        </ListItemIcon>
        <ListItemText
          primary={folder.name}
          secondary={trackCount > 0 ? `${trackCount}` : undefined}
          primaryTypographyProps={{ variant: 'body2', noWrap: true, fontWeight: isSelected ? 600 : 400 }}
          secondaryTypographyProps={{ variant: 'caption', sx: { color: isSelected ? 'primary.contrastText' : 'text.disabled', opacity: 0.8 } }}
        />
        <IconButton
          size="small"
          onClick={(e) => { e.stopPropagation(); setMenuAnchor(e.currentTarget); }}
          sx={{ opacity: 0, '.MuiListItemButton-root:hover &': { opacity: 1 }, color: 'inherit', p: 0.25 }}
        >
          <MoreVertIcon sx={{ fontSize: 16 }} />
        </IconButton>
      </ListItemButton>

      <Menu
        anchorEl={menuAnchor}
        open={!!menuAnchor}
        onClose={() => setMenuAnchor(null)}
        slotProps={{ paper: { sx: { minWidth: 150 } } }}
      >
        <MenuItem onClick={() => { onRename(folder); setMenuAnchor(null); }}>Umbenennen</MenuItem>
        <MenuItem onClick={() => { onDelete(folder); setMenuAnchor(null); }} sx={{ color: 'error.main' }}>Löschen</MenuItem>
      </Menu>

      {hasChildren && (
        <Collapse in={expanded} timeout="auto" unmountOnExit>
          {children.map((child) => (
            <TreeNode
              key={child.id}
              folder={child}
              folders={folders}
              allTracks={allTracks}
              currentFolderId={currentFolderId}
              depth={depth + 1}
              onNavigate={onNavigate}
              onRename={onRename}
              onDelete={onDelete}
            />
          ))}
        </Collapse>
      )}
    </>
  );
};

export const FolderTree: React.FC<FolderTreeProps> = ({
  folders, allTracks, currentFolderId, onNavigate, onRename, onDelete,
}) => {
  const { t } = useTranslation('media');
  const rootFolders = folders.filter((f) => f.parent_id == null);
  const rootTrackCount = allTracks.filter((t) => t.folder_id == null).length;

  return (
    <Box
      sx={{
        width: '100%',
        height: '100%',
        overflowY: 'auto',
        borderRight: 1,
        borderColor: 'divider',
        bgcolor: 'background.paper',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <Typography
        variant="overline"
        sx={{ px: 2, pt: 1.5, pb: 0.5, color: 'text.secondary', letterSpacing: 1, fontSize: '0.65rem' }}
      >
        {t('tabs.tracks')}
      </Typography>

      {/* Root / All tracks */}
      <ListItemButton
        selected={currentFolderId === null}
        onClick={() => onNavigate(null)}
        sx={{
          pl: 1.5, pr: 0.5, py: 0.4, borderRadius: 1, mx: 0.5,
          '&.Mui-selected': { bgcolor: 'primary.main', color: 'primary.contrastText',
            '& .MuiListItemIcon-root': { color: 'primary.contrastText' },
            '&:hover': { bgcolor: 'primary.dark' },
          },
        }}
      >
        <ListItemIcon sx={{ minWidth: 28 }}>
          <LibraryMusicIcon sx={{ fontSize: 18 }} />
        </ListItemIcon>
        <ListItemText
          primary={t('folders.root', { defaultValue: 'Alle Tracks' })}
          secondary={rootTrackCount > 0 ? `${rootTrackCount}` : undefined}
          primaryTypographyProps={{ variant: 'body2', fontWeight: currentFolderId === null ? 600 : 400 }}
          secondaryTypographyProps={{ variant: 'caption', sx: { color: currentFolderId === null ? 'primary.contrastText' : 'text.disabled', opacity: 0.8 } }}
        />
      </ListItemButton>

      {rootFolders.map((folder) => (
        <TreeNode
          key={folder.id}
          folder={folder}
          folders={folders}
          allTracks={allTracks}
          currentFolderId={currentFolderId}
          depth={0}
          onNavigate={onNavigate}
          onRename={onRename}
          onDelete={onDelete}
        />
      ))}

      {rootFolders.length === 0 && (
        <Tooltip title={t('folders.create_title', { defaultValue: 'Ordner erstellen' })}>
          <Typography
            variant="caption"
            color="text.disabled"
            sx={{ px: 2, py: 2, display: 'block', fontStyle: 'italic' }}
          >
            {t('folders.empty_hint', { defaultValue: 'Noch keine Ordner. Nutze den + Button.' })}
          </Typography>
        </Tooltip>
      )}
    </Box>
  );
};
