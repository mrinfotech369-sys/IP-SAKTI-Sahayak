'use client';

import clsx from 'clsx';
import { AlertTriangle, CheckCircle2, CircleHelp, Loader2, RefreshCw, XCircle } from 'lucide-react';
import Link from 'next/link';
import { ReactNode, useEffect } from 'react';
import { ApiError } from '@/lib/api';
import { useApp } from '@/lib/providers';

export const cx = clsx;

export function Button({
  children, variant = 'primary', size = 'md', className, loading, ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'secondary' | 'ghost' | 'danger'; size?: 'sm' | 'md'; loading?: boolean }) {
  return (
    <button
      {...rest}
      disabled={rest.disabled || loading}
      className={cx(
        'inline-flex items-center justify-center gap-1.5 rounded-md font-medium transition disabled:opacity-50 disabled:cursor-not-allowed',
        size === 'sm' ? 'px-2.5 py-1 text-xs' : 'px-4 py-2 text-sm',
        variant === 'primary' && 'bg-deep-green text-white hover:bg-green',
        variant === 'secondary' && 'border border-surface-border bg-surface-elevated text-text-main hover:bg-surface-muted',
        variant === 'ghost' && 'text-text-secondary hover:bg-surface-muted hover:text-text-main',
        variant === 'danger' && 'bg-danger text-white hover:opacity-90',
        className
      )}
    >
      {loading && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
      {children}
    </button>
  );
}

export function LinkButton({ href, children, variant = 'primary', className }: { href: string; children: ReactNode; variant?: 'primary' | 'secondary'; className?: string }) {
  return (
    <Link
      href={href}
      className={cx(
        'inline-flex items-center justify-center gap-1.5 rounded-md px-4 py-2 text-sm font-medium transition',
        variant === 'primary' ? 'bg-deep-green text-white hover:bg-green' : 'border border-surface-border bg-surface-elevated hover:bg-surface-muted',
        className
      )}
    >
      {children}
    </Link>
  );
}

export function Card({ children, className, title, actions, subtitle }: { children: ReactNode; className?: string; title?: ReactNode; actions?: ReactNode; subtitle?: ReactNode }) {
  return (
    <section className={cx('rounded-lg border border-surface-border bg-surface-elevated', className)}>
      {(title || actions) && (
        <header className="flex items-start justify-between gap-3 border-b border-surface-border px-4 py-3">
          <div>
            {title && <h2 className="text-sm font-semibold">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-xs text-text-muted">{subtitle}</p>}
          </div>
          {actions && <div className="flex shrink-0 gap-2">{actions}</div>}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

const TONES = {
  neutral: 'bg-surface-muted text-text-secondary border-surface-border',
  ok: 'bg-ok-bg text-ok border-ok/20',
  warn: 'bg-warn-bg text-warn border-warn/20',
  danger: 'bg-danger-bg text-danger border-danger/20',
  info: 'bg-info-bg text-info border-info/20',
  gold: 'bg-[#F6EDD5] text-[#7A5B12] border-gold/30',
  dark: 'bg-deep-green text-white border-deep-green',
};

export function Badge({ children, tone = 'neutral', className, title }: { children: ReactNode; tone?: keyof typeof TONES; className?: string; title?: string }) {
  return (
    <span title={title} className={cx('inline-flex items-center gap-1 whitespace-nowrap rounded border px-1.5 py-0.5 text-[11px] font-medium', TONES[tone], className)}>
      {children}
    </span>
  );
}

export function TierBadge({ tier }: { tier: number }) {
  const labels: Record<number, string> = { 1: 'Official law / regulator', 2: 'International official', 3: 'Peer-reviewed', 4: 'Secondary / demo', 5: 'User-provided / unverified' };
  return (
    <Badge tone={tier === 1 ? 'dark' : tier === 2 ? 'info' : tier === 3 ? 'ok' : tier === 4 ? 'gold' : 'warn'} title={labels[tier]}>
      Tier {tier}
    </Badge>
  );
}

export function FreshnessBadge({ status }: { status: string }) {
  const tone = status === 'Current' ? 'ok' : status === 'Recently checked' ? 'info' : status === 'Superseded' ? 'danger' : 'warn';
  return <Badge tone={tone}>{status}</Badge>;
}

export function DemoBadge({ reviewStatus }: { reviewStatus?: string }) {
  const { t } = useApp();
  if (reviewStatus === 'DEMO_FICTIONAL') return <Badge tone="warn" title="Fictional record for demonstration">{t.demo} · fictional</Badge>;
  if (reviewStatus === 'SEED_SUMMARY') return <Badge tone="gold" title="Seed summary of a real instrument — verify against the official text">Seed summary · verify</Badge>;
  if (reviewStatus === 'PENDING_REVIEW') return <Badge tone="warn">Unverified upload</Badge>;
  return null;
}

const STATUS_TONE: Record<string, keyof typeof TONES> = {
  SUPPORTED: 'ok', PARTIALLY_SUPPORTED: 'warn', UNSUPPORTED: 'danger', CONFLICTING: 'danger', INSUFFICIENT: 'neutral',
};

export function SupportBadge({ status }: { status: string }) {
  const { t } = useApp();
  const Icon = status === 'SUPPORTED' ? CheckCircle2 : status === 'UNSUPPORTED' ? XCircle : status === 'INSUFFICIENT' ? CircleHelp : AlertTriangle;
  return (
    <Badge tone={STATUS_TONE[status] || 'neutral'}>
      <Icon className="h-3 w-3" aria-hidden />
      {(t.status[status] || status).replace(/^[✓⚠✕?]\s*/, '')}
    </Badge>
  );
}

export function SeverityBadge({ severity }: { severity: string }) {
  const tone = severity === 'CRITICAL' ? 'danger' : severity === 'HIGH' ? 'danger' : severity === 'MEDIUM' ? 'warn' : 'neutral';
  return <Badge tone={tone} className={severity === 'CRITICAL' ? 'font-bold' : ''}>{severity}</Badge>;
}

export function JurisdictionBadge({ j }: { j: string }) {
  const names: Record<string, string> = { IN: 'India', US: 'USA', AU: 'Australia', INTERNATIONAL: 'International', EP: 'Europe' };
  return <Badge tone="info">{names[j] || j}</Badge>;
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div role="status" className="flex items-center gap-2 text-sm text-text-secondary">
      <Loader2 className="h-4 w-4 animate-spin text-green" aria-hidden />
      {label || 'Loading…'}
    </div>
  );
}

export function ProgressSteps({ steps, active }: { steps: string[]; active: number }) {
  return (
    <ol className="space-y-1.5" aria-live="polite">
      {steps.map((s, i) => (
        <li key={s} className={cx('flex items-center gap-2 text-sm', i < active ? 'text-ok' : i === active ? 'text-text-main font-medium' : 'text-text-muted')}>
          {i < active ? <CheckCircle2 className="h-4 w-4" /> : i === active ? <Loader2 className="h-4 w-4 animate-spin" /> : <span className="h-4 w-4 rounded-full border border-surface-border" />}
          {s}
        </li>
      ))}
    </ol>
  );
}

/** Cycles through step labels while a long request runs (server work is not streamed). */
export function useStepTicker(running: boolean, n: number, setActive: (i: number) => void, ms = 700) {
  useEffect(() => {
    if (!running) return;
    setActive(0);
    let i = 0;
    const id = setInterval(() => {
      i = Math.min(i + 1, n - 1);
      setActive(i);
    }, ms);
    return () => clearInterval(id);
  }, [running, n, ms, setActive]);
}

export function EmptyState({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-surface-border bg-surface px-6 py-10 text-center">
      <p className="font-medium">{title}</p>
      {children && <div className="mx-auto mt-1 max-w-lg text-sm text-text-secondary">{children}</div>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const e = error instanceof ApiError ? error : null;
  const hint =
    e?.status === 403 ? 'Your role in this workspace does not allow this. Ask a workspace admin for access.'
      : e?.status === 404 ? 'It may have been deleted, or it belongs to a workspace you are not a member of.'
      : e?.code === 'NETWORK_ERROR' ? 'Start the backend (uvicorn) and Postgres (docker compose up -d postgres), then retry.'
      : e?.status && e.status >= 500 ? 'The server logged the error. Retry; if it persists, check System Health.'
      : null;
  return (
    <div role="alert" className="rounded-lg border border-danger/30 bg-danger-bg p-4 text-sm">
      <p className="font-semibold text-danger">{e?.message || (error as Error)?.message || 'Request failed.'}</p>
      {hint && <p className="mt-1 text-text-secondary">{hint}</p>}
      {e?.code && <p className="mt-1 font-mono text-[11px] text-text-muted">{e.code}</p>}
      {onRetry && (
        <Button variant="secondary" size="sm" className="mt-3" onClick={onRetry}>
          <RefreshCw className="h-3.5 w-3.5" /> Retry
        </Button>
      )}
    </div>
  );
}

export function PageHeader({ title, subtitle, actions, eyebrow }: { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode; eyebrow?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        {eyebrow && <div className="mb-1 text-xs font-semibold uppercase tracking-wider text-text-muted">{eyebrow}</div>}
        <h1 className="font-serif text-3xl leading-tight">{title}</h1>
        {subtitle && <p className="mt-1 max-w-3xl text-sm text-text-secondary">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

export function Stat({ label, value, hint, href }: { label: string; value: ReactNode; hint?: string; href?: string }) {
  const inner = (
    <div className="rounded-lg border border-surface-border bg-surface-elevated px-4 py-3 transition hover:border-green/40">
      <div className="text-xs font-medium text-text-secondary">{label}</div>
      <div className="mt-1 font-serif text-3xl tabular-nums">{value}</div>
      {hint && <div className="mt-0.5 text-[11px] text-text-muted">{hint}</div>}
    </div>
  );
  return href ? <Link href={href}>{inner}</Link> : inner;
}

export function Tabs({ tabs, active, onChange }: { tabs: { key: string; label: ReactNode }[]; active: string; onChange: (k: string) => void }) {
  return (
    <div role="tablist" className="flex flex-wrap gap-1 border-b border-surface-border">
      {tabs.map((tb) => (
        <button
          key={tb.key}
          role="tab"
          aria-selected={active === tb.key}
          onClick={() => onChange(tb.key)}
          className={cx('-mb-px border-b-2 px-3 py-2 text-sm', active === tb.key ? 'border-deep-green font-semibold text-deep-green' : 'border-transparent text-text-secondary hover:text-text-main')}
        >
          {tb.label}
        </button>
      ))}
    </div>
  );
}

export function Drawer({ open, onClose, title, children }: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode }) {
  useEffect(() => {
    if (!open) return;
    const h = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true" aria-label={typeof title === 'string' ? title : 'Details'}>
      <button className="absolute inset-0 bg-black/30" aria-label="Close" onClick={onClose} />
      <div className="relative flex h-full w-full max-w-xl flex-col bg-surface-elevated shadow-xl">
        <div className="flex items-center justify-between border-b border-surface-border px-5 py-3">
          <h2 className="font-semibold">{title}</h2>
          <Button variant="ghost" size="sm" onClick={onClose} aria-label="Close panel">✕</Button>
        </div>
        <div className="flex-1 overflow-y-auto p-5">{children}</div>
      </div>
    </div>
  );
}

export function Field({ label, children, hint, required }: { label: string; children: ReactNode; hint?: string; required?: boolean }) {
  return (
    <label className="block">
      <span className="label">
        {label}
        {required && <span className="text-danger"> *</span>}
      </span>
      {children}
      {hint && <span className="mt-1 block text-[11px] text-text-muted">{hint}</span>}
    </label>
  );
}

export function Notice({ tone = 'warn', children, title }: { tone?: 'warn' | 'info' | 'danger' | 'ok'; children: ReactNode; title?: string }) {
  return (
    <div role="note" className={cx('rounded-md border px-3 py-2 text-sm', TONES[tone])}>
      {title && <div className="font-semibold">{title}</div>}
      <div className={title ? 'mt-0.5' : ''}>{children}</div>
    </div>
  );
}

export function fmtDate(s?: string | null) {
  if (!s) return '—';
  const d = new Date(s);
  return isNaN(d.getTime()) ? s : d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

export function fmtDateTime(s?: string | null) {
  if (!s) return '—';
  return new Date(s).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
}
