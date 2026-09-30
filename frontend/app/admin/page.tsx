'use client';

import { useRouter } from 'next/navigation';
import { useEffect } from 'react';
import { Spinner } from '@/components/ui';
import { useAdmin } from '@/lib/admin';

/** /admin -> /admin/dashboard (or /admin/login, decided by the layout guard's session check). */
export default function AdminIndex() {
  const router = useRouter();
  const { session, loading } = useAdmin();
  useEffect(() => {
    if (!loading && session?.state === 'admin') router.replace('/admin/dashboard');
  }, [loading, session, router]);
  return <div className="grid min-h-[50vh] place-items-center"><Spinner /></div>;
}
