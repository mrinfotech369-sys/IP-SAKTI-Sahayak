'use client';

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Bot, Lock, RefreshCw } from 'lucide-react';
import Link from 'next/link';
import { useParams, usePathname } from 'next/navigation';
import { Badge, Button, ErrorState, JurisdictionBadge, LinkButton, Notice, Spinner, cx, fmtDateTime } from '@/components/ui';
import { BackLink } from '@/components/back';
import { post } from '@/lib/api';
import { useInnovation } from '@/lib/hooks';

const TABS = [
  ['', 'Summary'],
  ['profile', 'Profile'],
  ['evidence', 'Evidence Map'],
  ['scientific', 'Scientific'],
  ['patents', 'Patents & Prior Art'],
  ['tk', 'Traditional Knowledge'],
  ['classification', 'Classification'],
  ['regulatory', 'Regulatory Passport'],
  ['gaps', 'Gaps & Risk'],
  ['graph', 'Evidence Graph'],
  ['review', 'Escalation & Report'],
] as const;

export default function InnovationLayout({ children }: { children: React.ReactNode }) {
  const { id } = useParams<{ id: string }>();
  const path = usePathname();
  const qc = useQueryClient();
  const inn = useInnovation(id);
  const rerun = useMutation({
    mutationFn: () => post(`/innovations/${id}/analyze`),
    onSuccess: () => qc.invalidateQueries({ predicate: (q) => JSON.stringify(q.queryKey).includes(id) || q.queryKey[0] === 'dashboard' }),
  });

  if (inn.isLoading) return <Spinner label="Loading innovation…" />;
  if (inn.isError) return <ErrorState error={inn.error} onRetry={() => inn.refetch()} />;
  const d = inn.data!;
  const base = `/app/innovations/${id}`;
  const current = path.replace(base, '').replace(/^\//, '');

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <BackLink href="/app/innovations">All innovations</BackLink>
          <h1 className="mt-1 font-serif text-3xl leading-tight">{d.name}</h1>
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            <Badge tone="dark">{d.status.replace('_', ' ')}</Badge>
            {d.jurisdictions.map((j) => <JurisdictionBadge key={j} j={j} />)}
            {d.is_demo && <Badge tone="warn">DEMO DATA · fictional innovation</Badge>}
            {d.confidentiality_level === 'CONFIDENTIAL' && <Badge tone="danger"><Lock className="h-3 w-3" /> Confidential</Badge>}
            <span className="text-xs text-text-muted">Completion {d.completion.percent}% · last analysed {fmtDateTime(d.analysis.last_run_at)}</span>
          </div>
        </div>
        <div className="flex gap-2">
          <LinkButton href={`/app/assistant?innovation=${id}`} variant="secondary"><Bot className="h-4 w-4" /> Ask about this innovation</LinkButton>
          <Button variant="secondary" onClick={() => rerun.mutate()} loading={rerun.isPending} disabled={!d.profile}>
            <RefreshCw className="h-4 w-4" /> Re-run analysis
          </Button>
        </div>
      </div>
      {d.confidential_warning && <div className="mb-3"><Notice tone="danger" title="Confidential innovation">{d.confidential_warning}</Notice></div>}
      {rerun.isError && <div className="mb-3"><ErrorState error={rerun.error} /></div>}
      {rerun.isSuccess && <div className="mb-3"><Notice tone="ok">Analysis re-run in {(rerun.data as any).latency_ms} ms: evidence, patent matches, classification and gaps refreshed.</Notice></div>}
      <nav className="no-print mb-5 flex gap-1 overflow-x-auto border-b border-surface-border" aria-label="Innovation sections">
        {TABS.map(([slug, label]) => (
          <Link key={slug} href={slug ? `${base}/${slug}` : base} aria-current={current === slug ? 'page' : undefined}
            className={cx('-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-sm', current === slug ? 'border-deep-green font-semibold text-deep-green' : 'border-transparent text-text-secondary hover:text-text-main')}>
            {label}
          </Link>
        ))}
      </nav>
      {children}
    </div>
  );
}
