import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useToast } from '@/contexts/ToastContext';
import { systemApi, type UpdateStatusResponse } from '@/api/system';
import { translateApiError } from '@/utils/apiError';

const POLL_MS = 2000;

export interface UpdateRun {
  /** True from starting the update until the box reports an exit code. */
  running: boolean;
  status: UpdateStatusResponse | null;
  progressOpen: boolean;
  closeProgress: () => void;
  /** Empty targets means "everything to latest". */
  start: (targets?: Record<string, string>) => Promise<void>;
}

/**
 * Startet ein Minabox-Update und verfolgt es bis zum Ende.
 *
 * Waehrend des Updates startet die Box Backend und WebUI neu - die Abfrage
 * schlaegt dann kurz fehl. Das ist kein Fehler, sondern der Neustart selbst,
 * also wird weiter gefragt und `unreachable` gesetzt.
 *
 * @param onFinished laeuft genau einmal je Lauf, nachdem der Endzustand feststeht.
 */
export function useUpdateRun(onFinished?: () => void): UpdateRun {
  const { t, i18n } = useTranslation('admin');
  const { showSuccess, showError } = useToast();
  const [running, setRunning] = useState(false);
  const [status, setStatus] = useState<UpdateStatusResponse | null>(null);
  const [progressOpen, setProgressOpen] = useState(false);
  // Ohne diesen Riegel feuert die 2-Sekunden-Abfrage die Erfolgsmeldung bei
  // jedem weiteren Durchlauf erneut (#137).
  const notifiedRef = useRef(false);
  const finishedRef = useRef(onFinished);
  finishedRef.current = onFinished;

  const start = useCallback(
    async (targets?: Record<string, string>) => {
      setRunning(true);
      setStatus(null);
      notifiedRef.current = false;
      try {
        await systemApi.updateMinabox(targets);
        // Der Aufruf kehrt sofort zurueck; ab hier zeigt das Fortschrittsfenster,
        // was passiert.
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
        const next = await systemApi.getUpdateStatus();
        if (!active) return;
        setStatus(next);
        if (next.running || next.exit_code === null) return;

        setRunning(false);
        // Endzustand nur einmal je Lauf melden und danach nicht mehr abfragen -
        // sonst wiederholt sich die Meldung im Sekundentakt (#137).
        stop();
        if (notifiedRef.current) return;
        notifiedRef.current = true;
        if (next.exit_code === 0) {
          showSuccess(t('system.update_success'));
          finishedRef.current?.();
        } else {
          showError(t('system.update_failed'));
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

  return { running, status, progressOpen, closeProgress, start };
}
