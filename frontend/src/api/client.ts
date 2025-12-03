import ky from 'ky';

let accessToken: string | null = null;
let _accessTokenExpiresAt: number | null = null; // Unix timestamp in milliseconds
let _refreshTimerId: any | null = null;
const refreshTokenKey = 'refresh_token';

// Clear any existing refresh timer
const clearRefreshTimer = () => {
  if (_refreshTimerId) {
    clearTimeout(_refreshTimerId);
    _refreshTimerId = null;
  }
};

export const setAccessToken = (token: string | null, expiresIn: number | null = null) => {
  accessToken = token;
  if (token && expiresIn) {
    _accessTokenExpiresAt = Date.now() + (expiresIn * 1000);
    scheduleTokenRefresh();
  } else {
    _accessTokenExpiresAt = null;
    clearRefreshTimer();
  }
};
export const getAccessToken = () => accessToken;
export const getRefreshToken = () => localStorage.getItem(refreshTokenKey);
export const setRefreshToken = (t: string | null) => {
  if (t) localStorage.setItem(refreshTokenKey, t);
  else localStorage.removeItem(refreshTokenKey);
};

let onUnauthorized: (() => void) | null = null;
export const setOnUnauthorized = (fn: (() => void) | null) => { onUnauthorized = fn; };

const handleUnauthorized = () => {
  setAccessToken(null); // This will also clear _accessTokenExpiresAt and refresh timer
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
        }).json<{ access_token: string; refresh_token: string; token_type: string; expires_in: number }>();
        
        setAccessToken(r.access_token, r.expires_in);
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
        } catch {
            // Silent fail on init - user will just be unauthenticated
            setRefreshToken(null);
            handleUnauthorized(); // Redirect if proactive refresh fails
        }
    }
};

// Schedule a proactive token refresh before it expires
const scheduleTokenRefresh = () => {
  clearRefreshTimer();
  if (_accessTokenExpiresAt) {
    const now = Date.now();
    // Refresh 5 minutes before actual expiration
    const refreshDelay = _accessTokenExpiresAt - now - (5 * 60 * 1000); 

    if (refreshDelay > 0) {
      _refreshTimerId = setTimeout(async () => {
        console.log("Proactively refreshing token...");
        // Re-call initializeAuth which will trigger refreshAuthToken
        // The singleton refreshPromise handles concurrent calls
        await initializeAuth(); 
      }, refreshDelay);
    } else {
      // If already expired or close to it, refresh immediately
      console.log("Token expired or close to expiration, refreshing immediately.");
      initializeAuth();
    }
  }
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

