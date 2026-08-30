import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import type { AxiosAdapter, InternalAxiosRequestConfig } from 'axios';
import { AxiosError } from 'axios';
import apiClient from './client';

/**
 * The retry policy is the reason W-01 existed: a POST that timed out was
 * repeated up to three times, so one failing upload sent the same file four
 * times. Only GET and HEAD may be repeated.
 *
 * Instead of pulling in a mock library the adapter is replaced - that is the
 * single place axios turns a config into a response, and it sees every retry.
 */
describe('apiClient retry policy', () => {
  const originalAdapter = apiClient.defaults.adapter;
  let calls: InternalAxiosRequestConfig[];

  /** An adapter that records every attempt and always fails the given way. */
  function failWith(code: string, status?: number): AxiosAdapter {
    return (config) => {
      calls.push(config);
      return Promise.reject(
        new AxiosError(
          `simulated ${code}`,
          code,
          config,
          {}, // truthy request: this is what marks a network error
          status === undefined
            ? undefined
            : { status, data: {}, statusText: '', headers: {}, config },
        ),
      );
    };
  }

  beforeEach(() => {
    calls = [];
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    apiClient.defaults.adapter = originalAdapter;
    vi.restoreAllMocks();
  });

  it('does not repeat a POST that ran into a network error', async () => {
    apiClient.defaults.adapter = failWith(AxiosError.ERR_NETWORK);
    await expect(apiClient.post('/tracks/upload')).rejects.toThrow();
    expect(calls).toHaveLength(1);
  });

  it('does not repeat a POST that timed out', async () => {
    apiClient.defaults.adapter = failWith(AxiosError.ECONNABORTED);
    await expect(apiClient.post('/system/backup/restore')).rejects.toThrow();
    expect(calls).toHaveLength(1);
  });

  it('does not repeat a DELETE that ran into a network error', async () => {
    apiClient.defaults.adapter = failWith(AxiosError.ERR_NETWORK);
    await expect(apiClient.delete('/tracks/1')).rejects.toThrow();
    expect(calls).toHaveLength(1);
  });

  it('does not repeat a POST that came back with a 500', async () => {
    apiClient.defaults.adapter = failWith(AxiosError.ERR_BAD_RESPONSE, 500);
    await expect(apiClient.post('/system/restart')).rejects.toThrow();
    expect(calls).toHaveLength(1);
  });

  it('repeats a GET that ran into a network error, then gives up', async () => {
    apiClient.defaults.adapter = failWith(AxiosError.ERR_NETWORK);
    await expect(apiClient.get('/system/status')).rejects.toThrow();
    // The original call plus RETRY_MAX_ATTEMPTS repeats.
    expect(calls).toHaveLength(4);
  }, 30_000);
});
