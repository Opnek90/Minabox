import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useToast } from '@/contexts/ToastContext';
import { systemApi, type UpdateStatusResponse } from '@/api/system';
import { translateApiError } from '@/utils/apiError';

const POLL_MS = 2000;

export interface UpdateRun {
  /** True from starting the update until the box reports an exit code. */
  running: boolean;
  /** What the current or last run was - the messages differ. */
  kind: 'update' | 'rollback';
  status: UpdateStatusResponse | null;
  progressOpen: boolean;
  closeProgress: () => void;
  /** Empty targets means "everything to latest". */
  start: (targets?: Record<string, string>) => Promise<void>;
  /** Put the named services back on the version they ran before. */
  startRollback: (services: string[]) => Promise<void>;
}

/**
 * Starts a Minabox update and follows it to the end.
 *
 * During the update the box restarts the backend and web UI - the poll then
 * fails briefly. That is not an error but the restart itself, so it keeps
 * polling and sets `unreachable`.
 *
 * @param onFinished runs exactly once per run, after the final state is known.
 */
export function useUpdateRun(onFinished?: () => void): UpdateRun {
  const { t, i18n } = useTranslation('admin');
  const { showSuccess, showError } = useToast();
  const [running, setRunning] = useState(false);
  const [status, setStatus] = useState<UpdateStatusResponse | null>(null);
  const [progressOpen, setProgressOpen] = useState(false);
  const [kind, setKind] = useState<'update' | 'rollback'>('update');
  // Without this latch the 2-second poll fires the success message again on
  // every further pass (#137).
  const notifiedRef = useRef(false);
  const finishedRef = useRef(onFinished);
  finishedRef.current = onFinished;
  // Read inside the poll, which must not restart when the kind changes.
  const kindRef = useRef(kind);
  kindRef.current = kind;

  // Both entry points do the same thing to the box - backup, pin, pull,
  // restart, verify - and are followed by the same poll. Only the tags differ.
  const begin = useCallback(
    async (next: 'update' | 'rollback', call: () => Promise<unknown>) => {
      setKind(next);
      setRunning(true);
      setStatus(null);
      notifiedRef.current = false;
      try {
        await call();
        // The call returns immediately; from here the progress window shows
        // what happens.
        setProgressOpen(true);
      } catch (err) {
        showError(translateApiError(t, i18n, err));
        setRunning(false);
      }
    },
    [showError, t, i18n],
  );

  const start = useCallback(
    (targets?: Record<string, string>) =>
      begin('update', () => systemApi.updateMinabox(targets)),
    [begin],
  );

  const startRollback = useCallback(
    (services: string[]) => begin('rollback', () => systemApi.rollback(services)),
    [begin],
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
        const next = await systemApi.getUpdateStatus();
        if (!active) return;
        setStatus(next);
        if (next.running || next.exit_code === null) return;

        setRunning(false);
        // Report the final state only once per run and stop polling after -
        // otherwise the message repeats every second (#137).
        stop();
        if (notifiedRef.current) return;
        notifiedRef.current = true;
        if (next.exit_code === 0) {
          showSuccess(t(kindRef.current === 'rollback' ? 'system.rollback_success' : 'system.update_success'));
          finishedRef.current?.();
        } else {
          showError(t(kindRef.current === 'rollback' ? 'system.rollback_failed' : 'system.update_failed'));
        }
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

  const closeProgress = useCallback(() => setProgressOpen(false), []);

  return { running, kind, status, progressOpen, closeProgress, start, startRollback };
}
