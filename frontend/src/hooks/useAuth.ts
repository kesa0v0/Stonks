import { useMutation } from '@tanstack/react-query';
import api, { setAccessToken, setRefreshToken } from '../api/client';

export function useAuth() {
  const login = useMutation({
    mutationFn: async (d: { username: string; password: string }) => {
      // OAuth2PasswordRequestForm 방식
      const body = new URLSearchParams();
      body.set('username', d.username);
      body.set('password', d.password);
      return api.post('auth/login/access-token', { body }).json<{access_token:string;refresh_token:string;token_type:string;expires_in:number}>();
    },
    onSuccess: t => {
      setAccessToken(t.access_token, t.expires_in);
      setRefreshToken(t.refresh_token);
    }
  });

  const getDiscordAuthorizeUrl = async () => {
    const r = await api.get('auth/discord/authorize').json<{ authorization_url: string }>();
    return r.authorization_url;
  };

  const exchangeDiscordCode = useMutation({
    mutationFn: (d: { code: string; redirect_uri?: string }) =>
      api.post('auth/discord/exchange', { json: d }).json<{access_token:string;refresh_token:string;token_type:string;expires_in:number}>(),
    onSuccess: t => {
      setAccessToken(t.access_token, t.expires_in);
      setRefreshToken(t.refresh_token);
    }
  });

  return { login, getDiscordAuthorizeUrl, exchangeDiscordCode };
}
