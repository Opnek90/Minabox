import { useCallback, useEffect, useState } from 'react';
import { configApi } from '@/api/config';
import { tagsApi } from '@/api/tags';

/**
 * Current version of the first-run wizard.
 *
 * If it is raised, the wizard offers itself again - meant for the case where a
 * release brings a genuinely new setup step. For anything smaller the value
 * stays; nobody wants to go through the wizard again after every update.
 */
export const SETUP_VERSION = 1;

export interface SetupStatus {
  /** true as long as the wizard should be offered. */
  needsSetup: boolean;
  loading: boolean;
  /** Re-read, e.g. after the wizard has been completed. */
  refresh: () => Promise<void>;
}

/**
 * Decides whether first-run setup is still pending.
 *
 * The special case is existing installations: their general_settings.json does
 * not know `setup_completed`, because the field did not exist before. An
 * already set-up box must not suddenly end up in the wizard because of that.
 * So a box counts as set up if it already has cards - nobody does that before
 * setup, and it needs no migration script.
 */
export function useSetupStatus(): SetupStatus {
  const [needsSetup, setNeedsSetup] = useState(false);
  const [loading, setLoading] = useState(true);

  const check = useCallback(async () => {
    setLoading(true);
    try {
      const general = await configApi.getGeneral();

      if (general.setup_completed && (general.setup_version ?? 0) >= SETUP_VERSION) {
        setNeedsSetup(false);
        return;
      }

      // The flag is missing entirely -> could be an existing installation.
      if (general.setup_completed === undefined) {
        try {
          const tags = await tagsApi.getAll();
          if (tags.length > 0) {
            setNeedsSetup(false);
            return;
          }
        } catch {
          // The tag query failed: then better not push it.
          setNeedsSetup(false);
          return;
        }
      }

      setNeedsSetup(true);
    } catch {
      // Backend unreachable: the wizard is not the most pressing problem, and
      // a false alarm would be worse than no hint at all.
      setNeedsSetup(false);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void check();
  }, [check]);

  return { needsSetup, loading, refresh: check };
}
