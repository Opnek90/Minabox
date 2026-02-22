import axios, { type InternalAxiosRequestConfig } from 'axios';
import type { ErrorResponse } from '@/types/api';

const RETRY_MAX_ATTEMPTS = 3;
const RETRY_DELAY_MS_INITIAL = 1000;
const RETRY_DELAY_MS_MAX = 10000;

function isRetryable(error: {
  response?: { status: number };
  request?: unknown;
  config?: InternalAxiosRequestConfig;
}): boolean {
  if (!error.config) return false;
  const config = error.config as InternalAxiosRequestConfig & { __retryCount?: number };
  if ((config.__retryCount ?? 0) >= RETRY_MAX_ATTEMPTS) return false;
  const method = (error.config.method ?? 'get').toLowerCase();
  const hasResponse = !!error.response;
  const networkError = !hasResponse && !!error.request;
  if (networkError) return true;
  if (!hasResponse) return false;
  const status = error.response!.status;
  const serverError = status >= 500 || status === 408;
  if (serverError && (method === 'get' || method === 'head')) return true;
  return false;
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export const apiClient = axios.create({
  baseURL: '/api/v1',
  timeout: 15000,
  headers: {
    'Content-Type': 'application/json',
  },
});

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const config = error.config as (InternalAxiosRequestConfig & { __retryCount?: number }) | undefined;
    const retryCount = config?.__retryCount ?? 0;

    if (config && isRetryable(error)) {
      config.__retryCount = retryCount + 1;
      const backoff = Math.min(
        RETRY_DELAY_MS_INITIAL * 2 ** retryCount,
        RETRY_DELAY_MS_MAX
      );
      await delay(backoff);
      return apiClient.request(config);
    }

    if (error.response) {
      const errorData = error.response.data as ErrorResponse;
      console.error('[WebUI] API Error:', errorData?.error || error.response.data);
    } else if (error.request) {
      console.error('[WebUI] Network Error:', error.message);
    } else {
      console.error('[WebUI] Request Error:', error.message);
    }
    return Promise.reject(error);
  }
);

export default apiClient;
