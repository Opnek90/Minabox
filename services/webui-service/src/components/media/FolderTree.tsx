import React, { useState } from 'react';
import {
  Box,
  Button,
  Collapse,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  IconButton,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Menu,
  MenuItem,
  Typography,
  useMediaQuery,
} from '@mui/material';
import ChevronRightIcon from '@mui/icons-material/ChevronRight';
import DeleteIcon from '@mui/icons-material/Delete';
import DriveFileRenameOutlineIcon from '@mui/icons-material/DriveFileRenameOutline';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import FolderIcon from '@mui/icons-material/Folder';
import FolderOpenIcon from '@mui/icons-material/FolderOpen';
import LibraryMusicIcon from '@mui/icons-material/LibraryMusic';
import MoreVertIcon from '@mui/icons-material/MoreVert';
import { useTranslation } from 'react-i18next';

const ROW_HEIGHT = 34;
const FONT_SIZE = '0.875rem';
const ICON_SIZE = 18;

/** Shared shape of Track-/Stream-/PodcastFolder - structurally identical on the backend. */
export interface MediaFolder {
  id: number;
  name: string;
  parent_id: number | null;
}

/** Minimal shape needed to count items per folder (Track/Stream/Podcast all have this). */
export interface MediaFolderItem {
  id: number;
  folder_id?: number | null;
}

interface FolderTreeProps {
  folders: MediaFolder[];
  items: MediaFolderItem[];
  currentFolderId: number | null;
  onNavigate: (folderId: number | null) => void;
  onRename: (folder: MediaFolder) => void;
  onDelete: (folder: MediaFolder) => void;
  /** Called when an item is dropped onto a folder (or root). */
  onDropItem?: (itemId: number, targetFolderId: number | null) => void;
  /** MIME type used for the drag payload, e.g. 'application/minabox-track-id'. */
  dragType: string;
  /** Header label above the tree, e.g. the tab name ("Tracks"/"Streams"/"Podcasts"). */
  treeLabel: string;
}

interface TreeNodeProps {
  folder: MediaFolder;
  folders: MediaFolder[];
  items: MediaFolderItem[];
  currentFolderId: number | null;
  depth: number;
  onNavigate: (folderId: number | null) => void;
  onRename: (folder: MediaFolder) => void;
  onDelete: (folder: MediaFolder) => void;
  onDropItem?: (itemId: number, targetFolderId: number | null) => void;
  dragType: string;
}

const TreeNode: React.FC<TreeNodeProps> = ({
  folder, folders, items, currentFolderId, depth,
  onNavigate, onRename, onDelete, onDropItem, dragType,
}) => {
  const { t } = useTranslation('media');
  const children = folders.filter((f) => f.parent_id === folder.id);
  const hasChildren = children.length > 0;
  const isSelected = currentFolderId === folder.id;
  const itemCount = items.filter((it) => it.folder_id === folder.id).length;

  const [expanded, setExpanded] = useState(true);
  const [menuAnchor, setMenuAnchor] = useState<HTMLElement | null>(null);
  const [hovered, setHovered] = useState(false);
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false);
  const [dragOver, setDragOver] = useState(false);

  const isTouch = useMediaQuery('(pointer: coarse)');
  const showButton = isTouch || hovered;

  const handleDeleteClick = () => {
    setMenuAnchor(null);
    setConfirmDeleteOpen(true);
  };

  const handleDeleteConfirm = () => {
    setConfirmDeleteOpen(false);
    onDelete(folder);
  };

  // --- Drag & Drop handlers ---
  const handleDragOver = (e: React.DragEvent) => {
    if (!e.dataTransfer.types.includes(dragType)) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    setDragOver(true);
  };

  const handleDragLeave = () => setDragOver(false);

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const rawId = e.dataTransfer.getData(dragType);
    const itemId = parseInt(rawId, 10);
    if (!isNaN(itemId) && onDropItem) {
      onDropItem(itemId, folder.id);
    }
  };

  return (
    <>
      <ListItemButton
        selected={isSelected}
        onClick={() => onNavigate(folder.id)}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        sx={{
          pl: 0.5 + depth * 1.5,
          pr: 0.5,
          minHeight: ROW_HEIGHT,
          maxHeight: ROW_HEIGHT,
          borderRadius: 0.75,
          mx: 0.5,
          outline: dragOver ? '2px solid' : 'none',
          outlineColor: dragOver ? 'primary.main' : 'transparent',
          bgcolor: dragOver ? 'primary.light' : undefined,
          transition: 'outline 0.1s, background-color 0.1s',
          '&.Mui-selected': {
            bgcolor: dragOver ? 'primary.light' : 'primary.main',
            color: 'primary.contrastText',
            '& .MuiListItemIcon-root': { color: 'primary.contrastText' },
            '&:hover': { bgcolor: 'primary.dark' },
          },
        }}
      >
        <Box sx={{ width: 18, flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          {hasChildren ? (
            <IconButton size="small" onClick={(e) => { e.stopPropagation(); setExpanded((v) => !v); }} sx={{ p: 0, color: 'inherit' }}>
              {expanded ? <ExpandMoreIcon sx={{ fontSize: ICON_SIZE }} /> : <ChevronRightIcon sx={{ fontSize: ICON_SIZE }} />}
            </IconButton>
          ) : null}
        </Box>

        <ListItemIcon sx={{ minWidth: 22, mr: 1 }}>
          {isSelected ? <FolderOpenIcon sx={{ fontSize: ICON_SIZE }} /> : <FolderIcon sx={{ fontSize: ICON_SIZE }} />}
        </ListItemIcon>

        <ListItemText
          primary={
            <Box component="span" sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
              <Typography component="span" sx={{ fontSize: FONT_SIZE, lineHeight: 1, fontWeight: isSelected ? 600 : 400 }} noWrap>
                {folder.name}
              </Typography>
              {itemCount > 0 && (
                <Typography component="span" sx={{ fontSize: '0.72rem', lineHeight: 1, color: isSelected ? 'primary.contrastText' : 'text.disabled', opacity: 0.8 }}>
                  {itemCount}
                </Typography>
              )}
            </Box>
          }
          disableTypography
        />

        <IconButton
          size="small"
          onClick={(e) => { e.stopPropagation(); setMenuAnchor(e.currentTarget); }}
          sx={{
            p: 0.25,
            color: 'inherit',
            flexShrink: 0,
            ml: 0.25,
            opacity: showButton ? 1 : 0,
            transition: 'opacity 0.15s',
            pointerEvents: showButton ? 'auto' : 'none',
          }}
          tabIndex={showButton ? 0 : -1}
          aria-hidden={!showButton}
        >
          <MoreVertIcon sx={{ fontSize: ICON_SIZE }} />
        </IconButton>
      </ListItemButton>

      <Menu
        anchorEl={menuAnchor}
        open={!!menuAnchor}
        onClose={() => setMenuAnchor(null)}
        anchorReference="anchorPosition"
        anchorPosition={menuAnchor ? {
          top: menuAnchor.getBoundingClientRect().bottom + 4,
          left: menuAnchor.getBoundingClientRect().left,
        } : undefined}
        transformOrigin={{ vertical: 'top', horizontal: 'right' }}
        slotProps={{ paper: { sx: { minWidth: 160 } } }}
      >
        <MenuItem dense onClick={() => { onRename(folder); setMenuAnchor(null); }}>
          <DriveFileRenameOutlineIcon fontSize="small" sx={{ mr: 1 }} />
          {t('folders.rename')}
        </MenuItem>
        <MenuItem dense onClick={handleDeleteClick} sx={{ color: 'error.main' }}>
          <DeleteIcon fontSize="small" sx={{ mr: 1 }} />
          {t('folders.delete')}
        </MenuItem>
      </Menu>

      <Dialog open={confirmDeleteOpen} onClose={() => setConfirmDeleteOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>{t('folders.delete_confirm_title')}</DialogTitle>
        <DialogContent>
          <DialogContentText>
            {t('folders.delete_confirm_text', { name: folder.name })}
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmDeleteOpen(false)} color="inherit" size="small">
            {t('cancel', { ns: 'common' })}
          </Button>
          <Button onClick={handleDeleteConfirm} color="error" variant="contained" size="small">
            {t('delete', { ns: 'common' })}
          </Button>
        </DialogActions>
      </Dialog>

      {hasChildren && (
        <Collapse in={expanded} timeout="auto" unmountOnExit>
          {children.map((child) => (
            <TreeNode
              key={child.id}
              folder={child}
              folders={folders}
              items={items}
              currentFolderId={currentFolderId}
              depth={depth + 1}
              onNavigate={onNavigate}
              onRename={onRename}
              onDelete={onDelete}
              onDropItem={onDropItem}
              dragType={dragType}
            />
          ))}
        </Collapse>
      )}
    </>
  );
};

export const FolderTree: React.FC<FolderTreeProps> = ({
  folders, items, currentFolderId, onNavigate, onRename, onDelete, onDropItem, dragType, treeLabel,
}) => {
  const { t } = useTranslation('media');
  const rootFolders = folders.filter((f) => f.parent_id == null);
  const rootItemCount = items.filter((it) => it.folder_id == null).length;

  const [rootDragOver, setRootDragOver] = useState(false);

  const handleRootDragOver = (e: React.DragEvent) => {
    if (!e.dataTransfer.types.includes(dragType)) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    setRootDragOver(true);
  };

  const handleRootDragLeave = () => setRootDragOver(false);

  const handleRootDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setRootDragOver(false);
    const rawId = e.dataTransfer.getData(dragType);
    const itemId = parseInt(rawId, 10);
    if (!isNaN(itemId) && onDropItem) {
      onDropItem(itemId, null);
    }
  };

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
        sx={{ px: 1.5, pt: 0.5, pb: 0.25, color: 'text.disabled', letterSpacing: 0.8, fontSize: '0.65rem', lineHeight: 1.5, display: 'block' }}
      >
        {treeLabel}
      </Typography>

      {/* Root Drop Target */}
      <ListItemButton
        selected={currentFolderId === null}
        onClick={() => onNavigate(null)}
        onDragOver={handleRootDragOver}
        onDragLeave={handleRootDragLeave}
        onDrop={handleRootDrop}
        sx={{
          pl: 0.5, pr: 0.5,
          minHeight: ROW_HEIGHT,
          maxHeight: ROW_HEIGHT,
          borderRadius: 0.75,
          mx: 0.5,
          outline: rootDragOver ? '2px solid' : 'none',
          outlineColor: rootDragOver ? 'primary.main' : 'transparent',
          bgcolor: rootDragOver ? 'primary.light' : undefined,
          transition: 'outline 0.1s, background-color 0.1s',
          '&.Mui-selected': {
            bgcolor: rootDragOver ? 'primary.light' : 'primary.main',
            color: 'primary.contrastText',
            '& .MuiListItemIcon-root': { color: 'primary.contrastText' },
            '&:hover': { bgcolor: 'primary.dark' },
          },
        }}
      >
        <Box sx={{ width: 18, flexShrink: 0 }} />
        <ListItemIcon sx={{ minWidth: 22, mr: 1 }}>
          <LibraryMusicIcon sx={{ fontSize: ICON_SIZE }} />
        </ListItemIcon>
        <ListItemText
          primary={
            <Box component="span" sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
              <Typography component="span" sx={{ fontSize: FONT_SIZE, lineHeight: 1, fontWeight: currentFolderId === null ? 600 : 400 }} noWrap>
                {t('folders.root')}
              </Typography>
              {rootItemCount > 0 && (
                <Typography component="span" sx={{ fontSize: '0.72rem', lineHeight: 1, color: currentFolderId === null ? 'primary.contrastText' : 'text.disabled', opacity: 0.8 }}>
                  {rootItemCount}
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
          items={items}
          currentFolderId={currentFolderId}
          depth={0}
          onNavigate={onNavigate}
          onRename={onRename}
          onDelete={onDelete}
          onDropItem={onDropItem}
          dragType={dragType}
        />
      ))}

      {rootFolders.length === 0 && (
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ px: 1.5, py: 1.5, display: 'block' }}
        >
          {t('folders.empty_hint')}
        </Typography>
      )}
    </Box>
  );
};
