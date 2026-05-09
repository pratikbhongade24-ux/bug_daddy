'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { ACCESS_TOKEN_KEY, USER_KEY } from '@/lib/storage';

export default function Home() {
  const router = useRouter();

  useEffect(() => {
    const hasSession = localStorage.getItem(USER_KEY) && localStorage.getItem(ACCESS_TOKEN_KEY);
    router.replace(hasSession ? '/dashboard' : '/login');
  }, [router]);

  return null;
}
