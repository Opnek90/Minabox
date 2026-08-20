import { useCallback, useEffect, useState } from 'react';
import { configApi } from '@/api/config';
import { tagsApi } from '@/api/tags';

/**
 * Aktuelle Version des Ersteinrichtungs-Assistenten.
 *
 * Wird sie erhoeht, bietet sich der Assistent erneut an - gedacht fuer den
 * Fall, dass ein Release einen wirklich neuen Einrichtungsschritt mitbringt.
 * Fuer alles Kleinere bleibt der Wert stehen; niemand moechte nach jedem
 * Update wieder durch den Assistenten.
 */
export const SETUP_VERSION = 1;

export interface SetupStatus {
  /** true, solange der Assistent angeboten werden soll. */
  needsSetup: boolean;
  loading: boolean;
  /** Neu einlesen, z. B. nachdem der Assistent abgeschlossen wurde. */
  refresh: () => Promise<void>;
}

/**
 * Entscheidet, ob die Ersteinrichtung noch aussteht.
 *
 * Der Sonderfall sind Bestandsinstallationen: deren general_settings.json kennt
 * `setup_completed` nicht, weil es das Feld frueher nicht gab. Eine bereits
 * eingerichtete Box duerfte dadurch nicht ploetzlich im Assistenten landen.
 * Deshalb gilt als eingerichtet, wer bereits Karten angelegt hat - das tut
 * niemand vor der Einrichtung, und es braucht kein Migrationsskript.
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

      // Flag fehlt komplett -> koennte eine Bestandsinstallation sein.
      if (general.setup_completed === undefined) {
        try {
          const tags = await tagsApi.getAll();
          if (tags.length > 0) {
            setNeedsSetup(false);
            return;
          }
        } catch {
          // Tag-Abfrage fehlgeschlagen: dann lieber nicht aufdraengen.
          setNeedsSetup(false);
          return;
        }
      }

      setNeedsSetup(true);
    } catch {
      // Backend nicht erreichbar: der Assistent ist nicht das dringendste
      // Problem, und ein Fehlalarm waere schlimmer als gar kein Hinweis.
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
