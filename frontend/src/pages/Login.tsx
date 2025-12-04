import { useState, useEffect } from 'react';
import { useAuth } from '../hooks/useAuth';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';

export default function Login() {
  const { getDiscordAuthorizeUrl, login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('test@kesa.uk');
  const [password, setPassword] = useState('test1234');
  const [error, setError] = useState<string | null>(null);
  const [showDev, setShowDev] = useState(false);
  const enablePassword = import.meta.env.VITE_ENABLE_PASSWORD_LOGIN === 'true';

  // Secret key combo: Ctrl+Alt+D toggles dev login
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.altKey && e.key.toLowerCase() === 'd') {
        setShowDev(prev => !prev);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);
  const handleDiscordLogin = async () => {
    try {
      const url = await getDiscordAuthorizeUrl();
      window.location.href = url;
    } catch (err) {
      console.error('Login failed', err);
      toast.error('Login configuration missing or API error.');
    }
  };

  const handlePasswordLogin = () => {
    setError(null);
    login.mutate(
      { username: email, password },
      {
        onSuccess: () => navigate('/dashboard'),
        onError: (e: unknown) => {
          if (e && typeof e === 'object' && 'message' in e) {
            setError(String((e as { message?: string }).message));
          } else {
            setError('Login failed');
          }
        }
      }
    );
  };

  return (
    <div className="relative flex h-screen w-full flex-col bg-[#101622] overflow-hidden font-sans items-center justify-center">
      {/* Background Grid Effect */}
      <div 
        className="absolute inset-0 z-0 opacity-10" 
        style={{ 
          backgroundImage: `linear-gradient(#314368 1px, transparent 1px), linear-gradient(90deg, #314368 1px, transparent 1px)`,
          backgroundSize: '3rem 3rem'
        }}
      ></div>
      
      {/* Glow Effect */}
      <div className="absolute inset-0 z-10 bg-gradient-to-br from-[#101622] via-transparent to-[#101622]"></div>

      {/* Login Card */}
      <div className="relative z-20 flex flex-col w-full max-w-md rounded-xl border border-[#314368] bg-[#101623]/80 backdrop-blur-lg p-8 shadow-2xl shadow-[#0d59f2]/10">
        <div className="text-center mb-8">
          <h1 className="text-white text-4xl font-black tracking-tighter mb-2">STONKS</h1>
          <p className="text-[#90a4cb] text-sm">Quant Trading Simulation Platform</p>
        </div>

        <div className="flex flex-col gap-4">
          {/* Hidden dev login (requires env flag + key combo) */}
          {enablePassword && showDev && (
            <>
              <div className="flex flex-col gap-2">
                <label className="text-xs font-bold text-[#90a4cb] uppercase">Email</label>
                <input
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  className="w-full bg-[#182234] border border-[#314368] rounded-lg px-3 py-2 text-white font-mono focus:border-[#0d59f2] focus:ring-1 focus:ring-[#0d59f2] outline-none transition-all"
                  placeholder="test@kesa.uk"
                  autoComplete="username"
                />
              </div>
              <div className="flex flex-col gap-2">
                <label className="text-xs font-bold text-[#90a4cb] uppercase">Password</label>
                <input
                  type="password"
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  className="w-full bg-[#182234] border border-[#314368] rounded-lg px-3 py-2 text-white font-mono focus:border-[#0d59f2] focus:ring-1 focus:ring-[#0d59f2] outline-none transition-all"
                  placeholder="••••••"
                  autoComplete="current-password"
                />
              </div>
              {error && <div className="text-red-500 text-xs font-medium">{error}</div>}
              <button
                onClick={handlePasswordLogin}
                disabled={login.isPending}
                className="w-full h-12 rounded-lg bg-[#0d59f2] text-white font-bold text-sm hover:bg-[#0d59f2]/90 transition-colors disabled:opacity-50"
              >
                {login.isPending ? 'Signing in...' : 'LOGIN'}
              </button>
              <div className="flex items-center gap-3 my-2">
                <div className="h-px bg-[#314368] flex-1" />
                <span className="text-[#90a4cb] text-xs">OR</span>
                <div className="h-px bg-[#314368] flex-1" />
              </div>
            </>
          )}
          <button 
            onClick={handleDiscordLogin}
            className="flex w-full items-center justify-center rounded-lg h-12 bg-[#5865F2] text-white text-sm font-bold transition-all duration-300 hover:bg-[#4752c4] hover:shadow-lg hover:shadow-[#5865F2]/30 group"
          >
            <svg className="w-5 h-5 mr-2 transition-transform group-hover:scale-110" fill="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
              <path d="M20.317 4.36981C18.7915 3.09531 16.9067 2.15571 14.8327 1.63581C14.6611 1.98251 14.4947 2.38501 14.3743 2.76611C12.8956 2.49251 11.4374 2.49251 9.95875 2.76611C9.83835 2.38501 9.67195 1.98251 9.50035 1.63581C7.42635 2.15571 5.54155 3.09531 4.01605 4.36981C1.69375 7.03571 0.76515 10.1556 1.13995 13.2195C2.94315 14.8335 5.00635 15.9392 7.18835 16.6322C7.54875 16.2042 7.87755 15.7548 8.16515 15.2741C7.62195 15.0729 7.09435 14.8303 6.59275 14.5513C6.72955 14.4285 6.86115 14.3005 6.98755 14.1673C10.4328 15.7608 13.8823 15.7608 17.3224 14.1673C17.4488 14.3005 17.5804 14.4285 17.7172 14.5513C17.2156 14.8303 16.688 15.0729 16.1448 15.2741C16.4324 15.7548 16.7612 16.2042 17.1216 16.6322C19.3036 15.9392 21.3668 14.8335 23.17 13.2195C23.633 9.44471 22.3444 6.37251 20.317 4.36981ZM8.44435 12.1625C7.65315 12.1625 7.01235 11.4933 7.01235 10.6691C7.01235 9.84491 7.65315 9.17571 8.44435 9.17571C9.23555 9.17571 9.87635 9.84491 9.87075 10.6691C9.87075 11.4933 9.23035 12.1625 8.44435 12.1625ZM15.8695 12.1625C15.0783 12.1625 14.4375 11.4933 14.4375 10.6691C14.4375 9.84491 15.0783 9.17571 15.8695 9.17571C16.6607 9.17571 17.3015 9.84491 17.2959 10.6691C17.2959 11.4933 16.6607 12.1625 15.8695 12.1625Z"></path>
            </svg>
            LOGIN WITH DISCORD
          </button>
          {enablePassword && (
            <div className="mt-2 text-center">
              <span className="text-[10px] text-[#314368] select-none cursor-default">
                Press <code>Ctrl+Alt+D</code> for dev login
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}