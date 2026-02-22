import { useState } from 'react';

export function useFormState() {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async (fn: () => Promise<void>) => {
    setSaving(true);
    setError(null);
    try {
      await fn();
    } catch (err) {
      const msg =
        err && typeof err === 'object' && 'response' in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : null;
      setError(msg ?? (err instanceof Error ? err.message : 'Fehler'));
      throw err; // re-throw so caller can bail out
    } finally {
      setSaving(false);
    }
  };

  return { saving, error, setError, run };
}
