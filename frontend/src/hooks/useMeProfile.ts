// frontend/src/hooks/useMeProfile.ts
import { useQuery } from '@tanstack/react-query';
import api from '../api/client';
import type { MeProfile } from '../interfaces';

export function useMeProfile() {
  const { data: meProfile, isLoading, isError } = useQuery<MeProfile, Error>({
    queryKey: ['meProfile'],
    queryFn: () => api.get('auth/login/me').json<MeProfile>(),
    staleTime: Infinity, // User profile data is relatively static and only changes on re-login
  });

  return { meProfile, isLoading, isError };
}
