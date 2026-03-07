import apiClient from './client';

export interface AuthConfig {
  authEnabled: boolean;
  protectedPaths: string[];
}

export async function getAuthConfig(): Promise<AuthConfig> {
  const response = await apiClient.get<AuthConfig>('/auth/config');
  return response.data;
}

export async function login(password: string): Promise<void> {
  await apiClient.post('/auth/login', { password });
}

export async function logout(): Promise<void> {
  await apiClient.post('/auth/logout');
}

export interface SetPasswordBody {
  current_password?: string;
  new_password: string;
}

export async function setPassword(body: SetPasswordBody): Promise<void> {
  await apiClient.post('/auth/password', body);
}

export interface AuthConfigUpdate {
  protected_areas: string[];
}

export async function updateAuthConfig(body: AuthConfigUpdate): Promise<AuthConfig> {
  const response = await apiClient.put<AuthConfig>('/auth/config', body);
  return response.data;
}

/** Löscht das WebUI-Passwort und deaktiviert den Zugriffsschutz vollständig. */
export async function resetAuth(): Promise<void> {
  await apiClient.delete('/auth/password');
}
