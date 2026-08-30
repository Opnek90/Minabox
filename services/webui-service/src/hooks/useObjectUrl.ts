import { useEffect, useState } from 'react';

/**
 * A preview URL for a locally picked file, released when it is no longer shown.
 *
 * `URL.createObjectURL()` is easy to call straight from JSX, and six dialogs
 * did exactly that. Each render then minted a fresh blob URL and none of them
 * was ever revoked, so picking a 2 MB cover and typing a title afterwards left
 * one copy per keystroke in memory until the tab was closed.
 *
 * Returns `null` when there is no file, so the caller can fall back to the URL
 * the entity already has.
 */
export function useObjectUrl(file: File | null | undefined): string | null {
  const [url, setUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!file) {
      setUrl(null);
      return;
    }
    const objectUrl = URL.createObjectURL(file);
    setUrl(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [file]);

  return url;
}
