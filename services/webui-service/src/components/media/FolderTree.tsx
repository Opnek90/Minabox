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

// Kompakte Zeilenöhe wie in VS Code Sidebar
const ROW_HEIGHT = 28;
const FONT_SIZE = '0.78rem';
const ICON_SIZE = 15;

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
  const [hovered, setHovered] = useState(false);

  return (
    <>
      <ListItemButton
        selected={isSelected}
        onClick={() => onNavigate(folder.id)}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        sx={{
          pl: 0.5 + depth * 1.5,
          pr: 0.5,
          minHeight: ROW_HEIGHT,
          maxHeight: ROW_HEIGHT,
          borderRadius: 0.75,
          mx: 0.5,
          '&.Mui-selected': {
            bgcolor: 'primary.main',
            color: 'primary.contrastText',
            '& .MuiListItemIcon-root': { color: 'primary.contrastText' },
            '&:hover': { bgcolor: 'primary.dark' },
          },
        }}
      >
        {/* Expand toggle or spacer */}
        <Box sx={{ width: 16, flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          {hasChildren ? (
            <IconButton
              size="small"
              onClick={(e) => { e.stopPropagation(); setExpanded((v) => !v); }}
              sx={{ p: 0, color: 'inherit' }}
            >
              {expanded
                ? <ExpandMoreIcon sx={{ fontSize: ICON_SIZE }} />
                : <ChevronRightIcon sx={{ fontSize: ICON_SIZE }} />}
            </IconButton>
          ) : null}
        </Box>

        <ListItemIcon sx={{ minWidth: 20, mr: 0.75 }}>
          {isSelected
            ? <FolderOpenIcon sx={{ fontSize: ICON_SIZE }} />
            : <FolderIcon sx={{ fontSize: ICON_SIZE }} />}
        </ListItemIcon>

        <ListItemText
          primary={
            <Box component="span" sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
              <Typography component="span" sx={{ fontSize: FONT_SIZE, lineHeight: 1, fontWeight: isSelected ? 600 : 400 }} noWrap>
                {folder.name}
              </Typography>
              {trackCount > 0 && (
                <Typography component="span" sx={{
                  fontSize: '0.65rem', lineHeight: 1,
                  color: isSelected ? 'primary.contrastText' : 'text.disabled',
                  opacity: 0.8,
                }}>
                  {trackCount}
                </Typography>
              )}
            </Box>
          }
          disableTypography
        />

        {/* Kontextmenü – nur bei Hover sichtbar */}
        {hovered && (
          <IconButton
            size="small"
            onClick={(e) => { e.stopPropagation(); setMenuAnchor(e.currentTarget); }}
            sx={{ p: 0.25, color: 'inherit', flexShrink: 0, ml: 0.25 }}
          >
            <MoreVertIcon sx={{ fontSize: ICON_SIZE }} />
          </IconButton>
        )}
      </ListItemButton>

      <Menu
        anchorEl={menuAnchor}
        open={!!menuAnchor}
        onClose={() => setMenuAnchor(null)}
        slotProps={{ paper: { sx: { minWidth: 150 } } }}
      >
        <MenuItem dense onClick={() => { onRename(folder); setMenuAnchor(null); }}>Umbenennen</MenuItem>
        <MenuItem dense onClick={() => { onDelete(folder); setMenuAnchor(null); }} sx={{ color: 'error.main' }}>Löschen</MenuItem>
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
        pt: 0.5,
      }}
    >
      <Typography
        variant="overline"
        sx={{
          px: 1.5, pt: 0.5, pb: 0.25,
          color: 'text.disabled',
          letterSpacing: 0.8,
          fontSize: '0.6rem',
          lineHeight: 1.5,
          display: 'block',
        }}
      >
        {t('tabs.tracks')}
      </Typography>

      {/* Root entry */}
      <ListItemButton
        selected={currentFolderId === null}
        onClick={() => onNavigate(null)}
        sx={{
          pl: 0.5, pr: 0.5,
          minHeight: ROW_HEIGHT,
          maxHeight: ROW_HEIGHT,
          borderRadius: 0.75,
          mx: 0.5,
          '&.Mui-selected': {
            bgcolor: 'primary.main',
            color: 'primary.contrastText',
            '& .MuiListItemIcon-root': { color: 'primary.contrastText' },
            '&:hover': { bgcolor: 'primary.dark' },
          },
        }}
      >
        {/* Spacer statt Expand-Toggle */}
        <Box sx={{ width: 16, flexShrink: 0 }} />
        <ListItemIcon sx={{ minWidth: 20, mr: 0.75 }}>
          <LibraryMusicIcon sx={{ fontSize: ICON_SIZE }} />
        </ListItemIcon>
        <ListItemText
          primary={
            <Box component="span" sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
              <Typography component="span" sx={{ fontSize: FONT_SIZE, lineHeight: 1, fontWeight: currentFolderId === null ? 600 : 400 }} noWrap>
                {t('folders.root', { defaultValue: 'Alle Tracks' })}
              </Typography>
              {rootTrackCount > 0 && (
                <Typography component="span" sx={{
                  fontSize: '0.65rem', lineHeight: 1,
                  color: currentFolderId === null ? 'primary.contrastText' : 'text.disabled',
                  opacity: 0.8,
                }}>
                  {rootTrackCount}
                </Typography>
              )}
            </Box>
          }
          disableTypography
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
            sx={{ px: 1.5, py: 1.5, display: 'block', fontStyle: 'italic', fontSize: '0.7rem' }}
          >
            {t('folders.empty_hint', { defaultValue: 'Noch keine Ordner.' })}
          </Typography>
        </Tooltip>
      )}
    </Box>
  );
};
