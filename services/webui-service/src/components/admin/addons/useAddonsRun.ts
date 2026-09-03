import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useToast } from '@/contexts/ToastContext';
import {
  addonsApi,
  type AddonProfile,
  type AddonsStatusResponse,
} from '@/api/addons';
import { translateApiError } from '@/utils/apiError';

const POLL_MS = 2000;

export interface AddonsRun {
  /** True from starting the change until the box reports an exit code. */
  running: boolean;
  status: AddonsStatusResponse | null;
  progressOpen: boolean;
  closeProgress: () => void;
  /** Set the components of this box to exactly these profiles. */
  start: (profiles: AddonProfile[]) => Promise<void>;
  /**
   * Follow a run that is already going - one started in another browser tab,
   * or this one after a reload. The run restarts the backend, so a page that
   * comes back mid-run is not an edge case.
   */
  attach: () => void;
}

/**
 * Switches components on and off and follows the run to the end.
 *
 * Same shape as `useUpdateRun`, and for the same reason: the run recreates the
 * backend, so the poll fails for a moment in the middle. That is the restart,
 * not an error - the hook keeps polling and marks the status `unreachable`.
 *
 * @param onFinished runs exactly once per run, after the final state is known.
 */
export function useAddonsRun(onFinished?: () => void): AddonsRun {
  const { t, i18n } = useTranslation('admin');
  const { showSuccess, showError } = useToast();
  const [running, setRunning] = useState(false);
  const [status, setStatus] = useState<AddonsStatusResponse | null>(null);
  const [progressOpen, setProgressOpen] = useState(false);
  // Without this latch the poll fires the message again on every further pass.
  const notifiedRef = useRef(false);
  const finishedRef = useRef(onFinished);
  finishedRef.current = onFinished;

  const start = useCallback(
    async (profiles: AddonProfile[]) => {
      setRunning(true);
      setStatus(null);
      notifiedRef.current = false;
      try {
        const started = await addonsApi.put(profiles);
        if (!started.changed) {
          // The box already had exactly this selection. Recreating containers
          // for that would restart the box for nothing.
          setRunning(false);
          finishedRef.current?.();
          return;
        }
        setProgressOpen(true);
      } catch (err) {
        showError(translateApiError(t, i18n, err));
        setRunning(false);
      }
    },
    [showError, t, i18n],
  );

  useEffect(() => {
    if (!progressOpen) return;
    let active = true;
    let interval: ReturnType<typeof setInterval> | undefined;
    const stop = () => {
      if (interval) {
        clearInterval(interval);
        interval = undefined;
      }
    };

    const poll = async () => {
      try {
        const next = await addonsApi.getStatus();
        if (!active) return;
        setStatus(next);
        if (next.running || next.exit_code === null) return;

        setRunning(false);
        stop();
        if (notifiedRef.current) return;
        notifiedRef.current = true;
        if (next.exit_code === 0) {
          showSuccess(t('system.components_success'));
        } else {
          showError(t('system.components_failed'));
        }
        // Either way: what the box has now is what the next read has to show.
        finishedRef.current?.();
      } catch {
        if (active) {
          setStatus((prev) => (prev ? { ...prev, unreachable: true } : prev));
        }
      }
    };

    void poll();
    interval = setInterval(poll, POLL_MS);
    return () => {
      active = false;
      stop();
    };
  }, [progressOpen, showSuccess, showError, t]);

  const attach = useCallback(() => {
    setRunning(true);
    notifiedRef.current = false;
    setProgressOpen(true);
  }, []);

  const closeProgress = useCallback(() => setProgressOpen(false), []);

  return { running, status, progressOpen, closeProgress, start, attach };
}
