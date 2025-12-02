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

const baseUrl = import.meta.env.VITE_API_BASE_URL as string;

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
          if (!rt) return;
          try {
            const r = await ky.post(`${baseUrl}/auth/login/refresh`, {
              json: { refresh_token: rt }
            }).json<{ access_token: string; refresh_token: string; token_type: string }>();
            setAccessToken(r.access_token);
            setRefreshToken(r.refresh_token);
            return ky(request);
          } catch {
            // fall through (unauthorized)
          }
        }
      }
    ]
  }
});

export default api;
