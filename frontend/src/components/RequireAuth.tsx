import { PropsWithChildren, useEffect, useState } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { getAccessToken, getRefreshToken } from '../api/client';

export default function RequireAuth({ children }: PropsWithChildren) {
  const location = useLocation();
  const [ready, setReady] = useState(false);
  const [authed, setAuthed] = useState(false);

  useEffect(() => {
    // simple check: access token in-memory or refresh token persisted
    const hasToken = !!getAccessToken() || !!getRefreshToken();
    setAuthed(hasToken);
    setReady(true);
  }, []);

  if (!ready) return null;
  if (!authed) return <Navigate to="/login" replace state={{ from: location }} />;
  return <>{children}</>;
}
