import { useEffect } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';

export default function OAuthCallback() {
  const [params] = useSearchParams();
  const code = params.get('code') || '';
  const navigate = useNavigate();
  const { exchangeDiscordCode } = useAuth();

  useEffect(() => {
    if (!code) return;
    exchangeDiscordCode.mutate(
      { code, redirect_uri: window.location.origin + '/auth/discord/callback' },
      { onSuccess: () => navigate('/') }
    );
  }, [code, exchangeDiscordCode, navigate]);

  return <div style={{ padding: 24 }}>Completing Discord sign-in...</div>;
}
