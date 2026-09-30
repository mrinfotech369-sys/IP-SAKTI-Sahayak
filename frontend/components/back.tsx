'use client';

import { ArrowLeft } from 'lucide-react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect } from 'react';
import { cx } from './ui';

const KEY = 'ipsakti.navStack';

function readStack(): string[] {
  try {
    return JSON.parse(sessionStorage.getItem(KEY) || '[]');
  } catch {
    return [];
  }
}

/** Keeps a stack of in-app paths so Back never leaves the site (e.g. when a page was opened from a shared link). */
export function useTrackNavigation() {
  const path = usePathname();
  useEffect(() => {
    const stack = readStack();
    if (stack[stack.length - 2] === path) stack.pop(); // a back navigation (button or browser)
    else if (stack[stack.length - 1] !== path) stack.push(path);
    try {
      sessionStorage.setItem(KEY, JSON.stringify(stack.slice(-50)));
    } catch {}
  }, [path]);
}

/** Parent route used when there is no in-app history to go back to. Covers both the user
 * app (/app/*) and the separate admin console (/admin/*) — the two never share a parent. */
export function parentPath(path: string): string {
  const parts = path.split('/').filter(Boolean);
  if (parts[0] === 'admin') {
    if (parts.length >= 3) return `/admin/${parts[1]}`; // e.g. /admin/escalations/{id} -> /admin/escalations
    return '/admin/dashboard';
  }
  if (parts[0] !== 'app') return '/';
  if (parts.length <= 1) return '/';
  if (parts[1] === 'innovations' && parts.length >= 3) return parts.length === 3 ? '/app/innovations' : `/app/innovations/${parts[2]}`;
  if (['reports', 'escalations', 'documents'].includes(parts[1]) && parts.length >= 3) return `/app/${parts[1]}`;
  return '/app';
}

export function BackButton({ fallback, label = 'Back', className }: { fallback?: string; label?: string; className?: string }) {
  const router = useRouter();
  const path = usePathname();
  function go() {
    if (readStack().length > 1) {
      router.back();
      return;
    }
    // No in-app history: go *up* to the parent and replace this entry, so repeated Back keeps climbing
    // (Graph → Summary → All innovations → Dashboard) instead of bouncing back down.
    try {
      sessionStorage.setItem(KEY, '[]');
    } catch {}
    router.replace(fallback || parentPath(path));
  }
  return (
    <button onClick={go} aria-label={label}
      className={cx('inline-flex items-center gap-1 rounded-md border border-surface-border bg-surface-elevated px-2 py-1 text-xs font-medium text-text-secondary hover:bg-surface-muted hover:text-text-main', className)}>
      <ArrowLeft className="h-3.5 w-3.5" aria-hidden /> {label}
    </button>
  );
}

/** Explicit link to a known parent page (used on detail pages). */
export function BackLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <Link href={href} className="inline-flex items-center gap-1 text-xs text-text-muted hover:text-text-main hover:underline">
      <ArrowLeft className="h-3 w-3" aria-hidden /> {children}
    </Link>
  );
}
