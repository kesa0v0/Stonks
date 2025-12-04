import { BrowserRouter, Routes, Route, Navigate, useNavigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Toaster } from 'react-hot-toast';
import { useEffect } from 'react';
import Dashboard from './pages/Dashboard';
import Leaderboards from './pages/Leaderboards';
import Portfolio from './pages/Portfolio';
import HumanETF from './pages/HumanETF';
import Market from './pages/Market';
import Login from './pages/Login';
import OAuthCallback from './pages/OAuthCallback';
import RequireAuth from './components/RequireAuth';
import Logout from './pages/Logout';
import { setOnUnauthorized, initializeAuth } from './api/client';

const queryClient = new QueryClient();

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Toaster position="top-right" />
      <BrowserRouter>
        <AuthBridge />
        <Routes>
          {/* Auth */}
          <Route path="/login" element={<Login />} />
          <Route path="/auth/discord/callback" element={<OAuthCallback />} />
          <Route path="/logout" element={<Logout />} />

          {/* App pages (protected) */}
          <Route path="/dashboard" element={<RequireAuth><Dashboard /></RequireAuth>} />
          <Route path="/market" element={<RequireAuth><Market /></RequireAuth>} />
          <Route path="/leaderboard" element={<RequireAuth><Leaderboards /></RequireAuth>} />
          <Route path="/portfolio" element={<RequireAuth><Portfolio /></RequireAuth>} />
          <Route path="/human" element={<RequireAuth><HumanETF /></RequireAuth>} />
          <Route path="/market/:tickerId" element={<RequireAuth><Market /></RequireAuth>} />

          {/* Default & Fallback */}
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

function AuthBridge() {
  const navigate = useNavigate();

  useEffect(() => {
    // Register a redirect handler for 401s from api client
    setOnUnauthorized(() => navigate('/login', { replace: true }));
    
    // Proactively refresh token on mount
    initializeAuth().catch(console.error);
  }, [navigate]);

  return null;
}