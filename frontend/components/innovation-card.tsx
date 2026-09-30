'use client';

import { Lock } from 'lucide-react';
import Link from 'next/link';
import type { InnovationCard } from '@/lib/types';
import { Badge, JurisdictionBadge, fmtDate } from './ui';

export function InnovationCardView({ inn }: { inn: InnovationCard }) {
  return (
    <Link href={`/app/innovations/${inn.id}`} className="block rounded-lg border border-surface-border bg-surface-elevated p-4 transition hover:border-green/50 hover:shadow-sm">
      <div className="flex items-start justify-between gap-2">
        <h3 className="font-semibold leading-snug">{inn.name}</h3>
        <div className="flex shrink-0 gap-1">
          {inn.is_demo && <Badge tone="warn">DEMO</Badge>}
          {inn.confidentiality_level === 'CONFIDENTIAL' && <Badge tone="danger"><Lock className="h-3 w-3" /> Confidential</Badge>}
        </div>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-1">
        <Badge tone="dark">{inn.status.replace('_', ' ')}</Badge>
        {inn.jurisdictions.map((j) => <JurisdictionBadge key={j} j={j} />)}
      </div>
      <dl className="mt-3 grid grid-cols-3 gap-2 text-center text-xs">
        <div className="rounded bg-surface-muted py-1.5"><dt className="text-text-muted">Evidence</dt><dd className="font-semibold tabular-nums">{inn.counts.evidence}</dd></div>
        <div className="rounded bg-surface-muted py-1.5"><dt className="text-text-muted">Patent matches</dt><dd className="font-semibold tabular-nums">{inn.counts.patent_matches}</dd></div>
        <div className="rounded bg-surface-muted py-1.5"><dt className="text-text-muted">Open gaps</dt><dd className="font-semibold tabular-nums">{inn.counts.evidence_gaps}</dd></div>
      </dl>
      <div className="mt-3">
        <div className="flex justify-between text-[11px] text-text-muted">
          <span>Completion {inn.completion.percent}%</span>
          <span>Updated {fmtDate(inn.updated_at)}</span>
        </div>
        <div className="mt-1 h-1.5 rounded bg-surface-muted" role="progressbar" aria-valuenow={inn.completion.percent} aria-valuemin={0} aria-valuemax={100}>
          <div className="h-1.5 rounded bg-green" style={{ width: `${inn.completion.percent}%` }} />
        </div>
      </div>
    </Link>
  );
}
