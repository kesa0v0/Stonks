import ky from 'ky';

let accessToken: string | null = null;
const refreshTokenKey = 'refresh_token';

export const setAccessToken = (t: string | null) => { accessToken = t; };
export const getAccessToken = () => accessToken;
export const getRefreshToken = () => localStorage.getItem(refreshTokenKey);
export const setRefreshToken = (t: string | null) => {
  if (t) localStorage.setItem(refreshTokenKey, t);
  else localStorage.removeItem(refreshTokenKey);
};

let onUnauthorized: (() => void) | null = null;
export const setOnUnauthorized = (fn: (() => void) | null) => { onUnauthorized = fn; };

const handleUnauthorized = () => {
  setAccessToken(null);
  setRefreshToken(null);
  if (onUnauthorized) onUnauthorized();
  else if (typeof window !== 'undefined' && window.location.pathname !== '/login') {
      window.location.href = '/login';
  }
};

const baseUrl = import.meta.env.VITE_API_BASE_URL as string;

// Singleton promise for refreshing token to avoid multiple concurrent refresh calls
let refreshPromise: Promise<void> | null = null;

const refreshAuthToken = async () => {
    const rt = getRefreshToken();
    if (!rt) {
        throw new Error('No refresh token');
    }

    try {
        const r = await ky.post(`${baseUrl}/auth/login/refresh`, {
            json: { refresh_token: rt }
        }).json<{ access_token: string; refresh_token: string; token_type: string }>();
        
        setAccessToken(r.access_token);
        setRefreshToken(r.refresh_token);
    } catch (error) {
        throw error;
    }
};

export const initializeAuth = async () => {
    const rt = getRefreshToken();
    if (rt && !accessToken) {
        try {
            await refreshAuthToken();
            return true; // Restored
        } catch {
            // Silent fail on init - user will just be unauthenticated
            setRefreshToken(null);
            return false;
        }
    }
    return !!accessToken;
};

const api = ky.create({
  prefixUrl: baseUrl,
  hooks: {
    beforeRequest: [
      request => {
        if (accessToken) {
          request.headers.set('Authorization', `Bearer ${accessToken}`);
        }
      }
    ],
    afterResponse: [
      async (request, _options, response) => {
        if (response.status === 401) {
          const rt = getRefreshToken();
          if (!rt) {
            handleUnauthorized();
            return;
          }

          // If a refresh is already in progress, wait for it
          if (!refreshPromise) {
              refreshPromise = refreshAuthToken().finally(() => {
                  refreshPromise = null;
              });
          }

          try {
            await refreshPromise;
            // Retry with new token
            // We need to explicitly set the new header because the original 'request' object
            // still has the old (or missing) header.
            if (accessToken) {
                request.headers.set('Authorization', `Bearer ${accessToken}`);
            }
            return ky(request);
          } catch {
            handleUnauthorized();
          }
        }
      }
    ]
  }
});

export default api;
