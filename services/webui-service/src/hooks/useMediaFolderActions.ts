import type { Dispatch, SetStateAction } from 'react';
import { useTranslation } from 'react-i18next';
import { useToast } from '@/contexts/ToastContext';
import type { MediaFolder } from '@/components/media/FolderTree';

/**
 * The slice of a folder API module these handlers need. Tracks, streams and
 * podcasts each have their own endpoints, but the same four operations.
 */
interface FolderApi<TFolder> {
  create: (data: { name: string; parent_id?: number | null }) => Promise<TFolder>;
  update: (id: number, data: { name?: string }) => Promise<TFolder>;
  delete: (id: number) => Promise<void>;
}

export interface MediaFolderActions<TItem> {
  create: (name: string, parentId: number | null) => Promise<void>;
  rename: (folder: MediaFolder, name: string) => Promise<void>;
  remove: (folder: MediaFolder) => Promise<void>;
  move: (item: TItem, folderId: number | null) => Promise<void>;
}

interface Config<TItem, TFolder> {
  foldersApi: FolderApi<TFolder>;
  setFolders: Dispatch<SetStateAction<TFolder[]>>;
  setItems: Dispatch<SetStateAction<TItem[]>>;
  /** Reloaded after a folder is deleted: the backend moves its items to the root. */
  reloadItems: () => Promise<TItem[]>;
  moveItem: (id: number, folderId: number | null) => Promise<TItem>;
  /** Toast after a successful move - the only message that names the media type. */
  movedMessage: string;
  moveErrorMessage: string;
}

/**
 * Create, rename, delete a media folder and move an item into one, including
 * the optimistic state updates and the toasts. One instance per media type.
 */
export function useMediaFolderActions<TItem extends { id: number }, TFolder extends MediaFolder>({
  foldersApi,
  setFolders,
  setItems,
  reloadItems,
  moveItem,
  movedMessage,
  moveErrorMessage,
}: Config<TItem, TFolder>): MediaFolderActions<TItem> {
  const { t } = useTranslation('media');
  const { showSuccess, showError } = useToast();

  return {
    create: async (name, parentId) => {
      try {
        const folder = await foldersApi.create({ name, parent_id: parentId });
        setFolders((prev) => [...prev, folder]);
        showSuccess(t('folders.created'));
      } catch {
        showError(t('folders.create_error'));
      }
    },

    rename: async (folder, name) => {
      try {
        const updated = await foldersApi.update(folder.id, { name });
        setFolders((prev) => prev.map((f) => (f.id === updated.id ? updated : f)));
        showSuccess(t('folders.renamed'));
      } catch {
        showError(t('folders.rename_error'));
      }
    },

    remove: async (folder) => {
      try {
        await foldersApi.delete(folder.id);
        setFolders((prev) => prev.filter((f) => f.id !== folder.id));
        setItems(await reloadItems());
        showSuccess(t('folders.deleted'));
      } catch {
        showError(t('folders.delete_error'));
      }
    },

    move: async (item, folderId) => {
      try {
        const updated = await moveItem(item.id, folderId);
        setItems((prev) => prev.map((i) => (i.id === updated.id ? updated : i)));
        showSuccess(movedMessage);
      } catch {
        showError(moveErrorMessage);
      }
    },
  };
}
