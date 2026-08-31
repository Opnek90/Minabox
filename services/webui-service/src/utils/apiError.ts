import type { TFunction, i18n as I18n } from 'i18next';

interface ApiErrorBody {
  code?: unknown;
  detail?: unknown;
}

function errorBody(err: unknown): ApiErrorBody | undefined {
  if (!err || typeof err !== 'object' || !('response' in err)) return undefined;
  const data = (err as { response?: { data?: unknown } }).response?.data;
  if (!data || typeof data !== 'object') return undefined;
  return data as ApiErrorBody;
}

/** Der stabile Backend-Code aus einer fehlgeschlagenen API-Antwort, falls vorhanden. */
export function apiErrorCode(err: unknown): string | undefined {
  const code = errorBody(err)?.code;
  return typeof code === 'string' ? code : undefined;
}

/**
 * Translates a failed API response via the `errors` namespace.
 *
 * `detail` is intentionally English and developer-oriented (logs, curl) - only
 * the translated `code` is shown. A code with no matching entry in errors.json
 * falls back to `errors:generic_error`, instead of showing a raw backend string
 * or no result at all.
 */
export function translateApiError(t: TFunction, i18n: I18n, err: unknown): string {
  const code = apiErrorCode(err);
  if (code && i18n.exists(`errors:${code}`)) {
    return t(`errors:${code}` as never);
  }
  return t('errors:generic_error' as never);
}
