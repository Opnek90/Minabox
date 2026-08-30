import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useToast } from '@/contexts/ToastContext';
import { useFormState } from '@/hooks/useFormState';
import { configApi } from '@/api/config';
import type { GeneralConfig } from '@/types/api';

/**
 * Shared loading and saving for the forms backed by `general_settings.json`.
 *
 * Seven settings forms carried the same twenty lines - load, fall back to a
 * default, catch into an error, save a partial patch, toast on success - and
 * the eight-to-thirty lines that differ were the actual form. They also each
 * issued their own `GET /config/general`, so opening a settings group fired
 * two or three identical requests at once.
 *
 * `pendingLoad` collapses those into one: mounts that overlap share the same
 * promise. It is deliberately not a cache - once the request settles the next
 * mount fetches again, so a form never shows a value another tab has since
 * changed.
 */
let pendingLoad: Promise<GeneralConfig> | null = null;

function loadGeneral(): Promise<GeneralConfig> {
  if (!pendingLoad) {
    pendingLoad = configApi.getGeneral().finally(() => {
      pendingLoad = null;
    });
  }
  return pendingLoad;
}

/**
 * The named fields with the types they have in `GeneralConfig` - not the
 * literal types the defaults happen to have. Without this a default of `false`
 * would make the field `false`, and the switch could never be turned on.
 */
export type GeneralFields<K extends keyof GeneralConfig> = {
  [P in K]-?: NonNullable<GeneralConfig[P]>;
};

export interface GeneralConfigFields<K extends keyof GeneralConfig> {
  /** `null` until the first load is through; render nothing while it is. */
  values: GeneralFields<K> | null;
  setValue: <P extends K>(key: P, value: NonNullable<GeneralConfig[P]>) => void;
  save: () => Promise<void>;
  saving: boolean;
  error: string | null;
}

/**
 * The named fields, each falling back to its default when the server has no
 * value for it. `save()` sends exactly these fields as a partial patch, so two
 * forms of the same group cannot overwrite each other.
 */
export function useGeneralConfigFields<K extends keyof GeneralConfig>(
  defaults: GeneralFields<K>,
): GeneralConfigFields<K> {
  const { t } = useTranslation('admin');
  const { showSuccess } = useToast();
  const { saving, error, setError, run } = useFormState();
  const [values, setValues] = useState<GeneralFields<K> | null>(null);

  // The defaults are written inline at the call site, so the object identity
  // changes on every render - the keys are what matters, and those are static.
  const keys = Object.keys(defaults) as K[];
  const keySignature = keys.join(',');

  useEffect(() => {
    let active = true;
    loadGeneral()
      .then((config) => {
        if (!active) return;
        const next = { ...defaults };
        for (const key of keys) {
          const fromServer = config[key];
          if (fromServer !== undefined && fromServer !== null) {
            next[key] = fromServer as GeneralFields<K>[K];
          }
        }
        setValues(next);
      })
      .catch(() => {
        if (active) setError(t('load_error'));
      });
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- keySignature stands
    // in for `defaults`, whose identity changes on every render; t and setError
    // would restart the load on a language switch for no gain.
  }, [keySignature]);

  const setValue = useCallback(<P extends K>(key: P, value: NonNullable<GeneralConfig[P]>) => {
    setValues((prev) => (prev ? { ...prev, [key]: value } : prev));
  }, []);

  const save = useCallback(
    () =>
      run(async () => {
        if (!values) return;
        await configApi.updateGeneral(values);
        setError(null);
        showSuccess(t('general.save_success'));
      }),
    [values, run, setError, showSuccess, t],
  );

  return { values, setValue, save, saving, error };
}

export interface GeneralConfigField<V> {
  /** `null` until the first load is through. */
  value: V | null;
  setValue: (value: V) => void;
  save: () => Promise<void>;
  saving: boolean;
  error: string | null;
}

/** One field, for the forms that edit exactly one. */
export function useGeneralConfigField<K extends keyof GeneralConfig>(
  key: K,
  fallback: NonNullable<GeneralConfig[K]>,
): GeneralConfigField<NonNullable<GeneralConfig[K]>> {
  const { values, setValue, save, saving, error } = useGeneralConfigFields<K>({
    [key]: fallback,
  } as GeneralFields<K>);

  return {
    value: values ? values[key] : null,
    setValue: (next) => setValue(key, next),
    save,
    saving,
    error,
  };
}
