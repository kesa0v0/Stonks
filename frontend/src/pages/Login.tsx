import { useState } from 'react';
import { useAuth } from '../hooks/useAuth';
import { useNavigate } from 'react-router-dom';

export default function Login() {
  const { login, getDiscordAuthorizeUrl } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');

  const handleDiscord = async () => {
    const url = await getDiscordAuthorizeUrl();
    window.location.href = url;
  };

  return (
    <div style={{ maxWidth: 360, margin: '80px auto', fontFamily: 'sans-serif' }}>
      <h2>Login</h2>
      <div style={{ display: 'grid', gap: 8 }}>
        <input placeholder="Email" value={username} onChange={e => setUsername(e.target.value)} />
        <input placeholder="Password" type="password" value={password} onChange={e => setPassword(e.target.value)} />
        <button
          disabled={login.isPending}
          onClick={() => login.mutate(
            { username, password },
            { onSuccess: () => navigate('/') }
          )}
        >
          {login.isPending ? 'Signing in...' : 'Sign in'}
        </button>
        <button onClick={handleDiscord}>Sign in with Discord</button>
      </div>
      {login.isError && <p style={{ color: 'crimson' }}>{(login.error as any)?.message || 'Login failed'}</p>}
    </div>
  );
}
