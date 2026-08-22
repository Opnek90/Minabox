import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { translateApiError } from '@/utils/apiError';

export function useFormState() {
  const { t, i18n } = useTranslation('errors');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async (fn: () => Promise<void>) => {
    setSaving(true);
    setError(null);
    try {
      await fn();
    } catch (err) {
      setError(translateApiError(t, i18n, err));
      throw err; // re-throw so caller can bail out
    } finally {
      setSaving(false);
    }
  };

  return { saving, error, setError, run };
}
