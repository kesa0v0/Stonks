import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { setAccessToken, setRefreshToken } from '../api/client';

export default function Logout() {
  const navigate = useNavigate();
  useEffect(() => {
    setAccessToken(null);
    setRefreshToken(null);
    navigate('/login', { replace: true });
  }, [navigate]);
  return null;
}
