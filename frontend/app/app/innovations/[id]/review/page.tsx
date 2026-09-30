'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { useState } from 'react';
import { Badge, Button, Card, EmptyState, ErrorState, Field, Notice, ProgressSteps, fmtDateTime, useStepTicker } from '@/components/ui';
import { get, post } from '@/lib/api';

const TYPES = [
  ['IP_REVIEW', 'Request IP Review', 'Patent agent / IP attorney reviews the prior-art matrix and TK exclusions.'],
  ['REGULATORY_REVIEW', 'Request Regulatory Review', 'Regulatory professional confirms the provisional pathway per market.'],
  ['DOMAIN_REVIEW', 'Request Domain Review', 'Ayurveda / botany expert confirms species identity and traditional use.'],
  ['HUMAN_REVIEW', 'Flag for Human Review', 'General review of any conclusion you are not comfortable relying on.'],
];

export default function ReviewTab() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const qc = useQueryClient();
  const [type, setType] = useState<string | null>(null);
  const [reason, setReason] = useState('');
  const [active, setActive] = useState(0);
  const escs = useQuery({ queryKey: ['innovation', id, 'escalations'], queryFn: () => get<any[]>(`/escalations?innovation_id=${id}`) });
  const reports = useQuery({ queryKey: ['innovation', id, 'reports'], queryFn: () => get<any[]>(`/reports?innovation_id=${id}`) });
  const create = useMutation({
    mutationFn: () => post<any>('/escalations', { innovation_id: id, type, reason }),
    onSuccess: (e) => { qc.invalidateQueries({ queryKey: ['innovation', id] }); router.push(`/app/escalations/${e.id}`); },
  });
  const report = useMutation({
    mutationFn: () => post<any>('/reports', { innovation_id: id }),
    onSuccess: (r) => { qc.invalidateQueries({ queryKey: ['innovation', id] }); router.push(`/app/reports/${r.id}`); },
  });
  const steps = ['Collecting profile & features…', 'Collecting patent findings…', 'Collecting scientific evidence…', 'Building regulatory passport…', 'Verifying citations…', 'Assembling report…'];
  useStepTicker(report.isPending, steps.length, setActive, 350);

  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <Card title="Human escalation" subtitle="Creates a review packet: profile, features, patent findings, science, regulatory findings, gaps, conflicts, open questions, citations and audit trail.">
        <div className="grid gap-2 sm:grid-cols-2">
          {TYPES.map(([k, label, desc]) => (
            <button key={k} onClick={() => setType(k)} aria-pressed={type === k}
              className={`rounded-md border p-3 text-left text-sm transition ${type === k ? 'border-deep-green bg-soft-green' : 'border-surface-border hover:border-green/40'}`}>
              <div className="font-semibold">{label}</div>
              <div className="mt-1 text-xs text-text-secondary">{desc}</div>
            </button>
          ))}
        </div>
        {type && (
          <div className="mt-3 space-y-2">
            <Field label="Reason" required><textarea className="w-full" rows={3} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="What should the reviewer focus on?" /></Field>
            <Button onClick={() => create.mutate()} loading={create.isPending} disabled={reason.trim().length < 3}>Create escalation packet</Button>
            {create.isError && <ErrorState error={create.error} />}
          </div>
        )}
        <div className="mt-5">
          <div className="label">Escalations for this innovation</div>
          {escs.data?.length === 0 && <p className="text-sm text-text-muted">None yet.</p>}
          <ul className="space-y-1.5 text-sm">
            {escs.data?.map((e) => (
              <li key={e.id} className="flex items-center justify-between rounded border border-surface-border px-2 py-1.5">
                <Link href={`/app/escalations/${e.id}`} className="hover:underline">{e.type.replace('_', ' ')} · {fmtDateTime(e.created_at)}</Link>
                <Badge tone={e.status === 'OPEN' ? 'warn' : e.status === 'IN_REVIEW' ? 'info' : 'ok'}>{e.status}</Badge>
              </li>
            ))}
          </ul>
        </div>
      </Card>
      <Card title="Evidence report" subtitle="Executive summary through audit metadata, with a generated-at timestamp. Export as Markdown or print to PDF.">
        <Notice tone="info">Reports include only configured-source evidence and label demo and unverified records.</Notice>
        <Button className="mt-3" onClick={() => report.mutate()} loading={report.isPending}>Generate evidence report</Button>
        {report.isPending && <div className="mt-3"><ProgressSteps steps={steps} active={active} /></div>}
        {report.isError && <div className="mt-3"><ErrorState error={report.error} /></div>}
        <div className="mt-5">
          <div className="label">Previous reports</div>
          {reports.isError && <ErrorState error={reports.error} />}
          {reports.data?.length === 0 && <EmptyState title="No reports yet" />}
          <ul className="space-y-1.5 text-sm">
            {reports.data?.map((r) => (
              <li key={r.id}><Link className="hover:underline" href={`/app/reports/${r.id}`}>{r.title} · {fmtDateTime(r.created_at)}</Link></li>
            ))}
          </ul>
        </div>
      </Card>
    </div>
  );
}
