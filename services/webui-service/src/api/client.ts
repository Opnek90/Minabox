import axios from 'axios';
import type { ErrorResponse } from '@/types/api';

export const apiClient = axios.create({
  baseURL: '/api/v1',
  timeout: 15000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Response interceptor for centralized error handling
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response) {
      // Backend responded with error
      const errorData = error.response.data as ErrorResponse;
      console.error('[WebUI] API Error:', errorData?.error || error.response.data);
    } else if (error.request) {
      // Request sent but no response received
      console.error('[WebUI] Network Error:', error.message);
    } else {
      // Error setting up request
      console.error('[WebUI] Request Error:', error.message);
    }
    return Promise.reject(error);
  }
);

export default apiClient;
