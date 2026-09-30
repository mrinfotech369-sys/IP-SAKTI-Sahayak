'use client';

import { useQueryClient } from '@tanstack/react-query';
import { ShieldCheck } from 'lucide-react';
import { useRouter, useSearchParams } from 'next/navigation';
import { FormEvent, Suspense, useState } from 'react';
import { Field, Notice } from '@/components/ui';
import { ApiError, post } from '@/lib/api';

export default function AdminLoginPage() {
  return (
    <Suspense>
      <AdminLoginForm />
    </Suspense>
  );
}

function AdminLoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const qc = useQueryClient();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const reason = params.get('reason');

  async function submit(e: FormEvent) {
    e.preventDefault();
    setErr(null);
    setBusy(true);
    try {
      await post('/auth/admin/login', { email, password });
      await qc.invalidateQueries({ queryKey: ['admin-session'] });
      router.push(params.get('next') || '/admin/dashboard');
    } catch (ex) {
      setErr(ex instanceof ApiError ? ex.message : 'Could not reach the server.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid min-h-screen place-items-center bg-[#14100a] px-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex items-center gap-2 text-white">
          <div className="grid h-8 w-8 place-items-center rounded bg-[#C9A24A] text-[#14100a]"><ShieldCheck className="h-4 w-4" /></div>
          <div className="leading-tight">
            <div className="font-semibold">IP-SAKTI Admin</div>
            <div className="text-[10px] uppercase tracking-widest text-white/40">Console sign-in</div>
          </div>
        </div>
        <div className="rounded-lg border border-white/10 bg-[#1A1108] p-6 text-white">
          <h1 className="font-serif text-2xl text-white">Admin sign in</h1>
          <p className="mt-1 text-xs text-white/60">
            This is a separate sign-in from the application. Only accounts with administrator access can use it, and the session it
            creates only works on <code>/admin/*</code> — it will not open a regular app session.
          </p>
          {reason === 'expired' && <div className="mt-3"><Notice tone="info">Your admin session expired. Please sign in again.</Notice></div>}
          <form onSubmit={submit} className="mt-4 space-y-3" noValidate>
            <Field label="Email" required>
              <input className="w-full bg-white/5 text-white placeholder:text-white/30" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" />
            </Field>
            <Field label="Password" required>
              <input className="w-full bg-white/5 text-white placeholder:text-white/30" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required autoComplete="current-password" />
            </Field>
            {err && <p role="alert" className="text-sm text-red-400">{err}</p>}
            <button type="submit" disabled={busy}
              className="w-full rounded-md bg-[#C9A24A] px-4 py-2 text-sm font-medium text-[#14100a] hover:bg-[#dab35c] disabled:opacity-50">
              {busy ? 'Signing in…' : 'Sign in to admin console'}
            </button>
          </form>
          <p className="mt-4 text-center text-xs text-white/40">
            Not an administrator? <a href="/login" className="underline">Go to the regular sign-in</a>.
          </p>
        </div>
      </div>
    </div>
  );
}
