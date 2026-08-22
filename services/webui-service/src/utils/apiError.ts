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
 * Uebersetzt eine fehlgeschlagene API-Antwort ueber den `errors`-Namespace.
 *
 * `detail` ist absichtlich englisch und entwicklerorientiert (Logs, curl) -
 * angezeigt wird ausschliesslich der uebersetzte `code`. Ein Code ohne
 * passenden Eintrag in errors.json faellt auf `errors:generic_error` zurueck,
 * statt einen rohen Backend-Text oder gar kein Ergebnis zu zeigen.
 */
export function translateApiError(t: TFunction, i18n: I18n, err: unknown): string {
  const code = apiErrorCode(err);
  if (code && i18n.exists(`errors:${code}`)) {
    return t(`errors:${code}` as never);
  }
  return t('errors:generic_error' as never);
}
