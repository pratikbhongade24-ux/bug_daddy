'use client';
import { useEffect } from 'react';

export default function Home() {
  useEffect(() => {
    const user = typeof window !== 'undefined' && localStorage.getItem('bugDaddyUser');
    if (user) {
      window.location.replace('/dashboard.html');
    } else {
      window.location.replace('/login.html');
    }
  }, []);

  return null;
}
