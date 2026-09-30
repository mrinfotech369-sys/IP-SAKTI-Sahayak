'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { FormEvent, useState } from 'react';
import { Badge, Button, Card, ErrorState, Field, PageHeader, Spinner, fmtDateTime } from '@/components/ui';
import { api, get } from '@/lib/api';

export default function AdminIngestion() {
  const qc = useQueryClient();
  const jobs = useQuery({ queryKey: ['jobs'], queryFn: () => get<any[]>('/ingestion-jobs'),
    refetchInterval: (qq) => ((qq.state.data as any[] | undefined)?.some((j) => ['PENDING', 'RUNNING'].includes(j.status)) ? 1000 : false) });
  const sources = useQuery({ queryKey: ['sources'], queryFn: () => get<any[]>('/sources') });
  const [file, setFile] = useState<File | null>(null);
  const [m, setM] = useState({ title: '', source_id: '', jurisdiction: 'IN', domain: 'REGULATORY', document_type: 'GUIDANCE', publication_date: '', effective_date: '', url: '' });
  const ingest = useMutation({
    mutationFn: () => { const fd = new FormData(); fd.append('file', file!); Object.entries(m).forEach(([k, v]) => v && fd.append(k, v)); return api('/documents/ingest', { form: fd }); },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['jobs'] }); setFile(null); },
    onError: () => qc.invalidateQueries({ queryKey: ['jobs'] }),
  });
  const set = (k: string) => (e: any) => setM({ ...m, [k]: e.target.value });
  return (
    <div className="space-y-5">
      <PageHeader eyebrow="Admin" title="Ingestion Jobs" subtitle="Ingest official documents into the global corpus: validate → hash → extract → section detection → clean → structure-aware chunk → injection scan → embed → index." />
      <Card title="Ingest into global corpus">
        <form onSubmit={(e: FormEvent) => { e.preventDefault(); ingest.mutate(); }} className="grid gap-3 md:grid-cols-4">
          <Field label="File (PDF/TXT/MD)" required><input type="file" accept=".pdf,.txt,.md" onChange={(e) => setFile(e.target.files?.[0] || null)} /></Field>
          <Field label="Title" required><input className="w-full" value={m.title} onChange={set('title')} /></Field>
          <Field label="Source" required><select className="w-full" value={m.source_id} onChange={set('source_id')}><option value="">Select…</option>{sources.data?.map((s) => <option key={s.id} value={s.id}>{s.name} (Tier {s.authority_tier})</option>)}</select></Field>
          <Field label="Jurisdiction"><select className="w-full" value={m.jurisdiction} onChange={set('jurisdiction')}>{['IN', 'US', 'AU', 'INTERNATIONAL'].map((x) => <option key={x}>{x}</option>)}</select></Field>
          <Field label="Domain"><select className="w-full" value={m.domain} onChange={set('domain')}>{['REGULATORY', 'IP', 'TK_ABS', 'SCIENTIFIC'].map((x) => <option key={x}>{x}</option>)}</select></Field>
          <Field label="Document type"><select className="w-full" value={m.document_type} onChange={set('document_type')}>{['LEGISLATION', 'RULES', 'REGULATION', 'GUIDANCE', 'TREATY', 'STUDY', 'PATENT', 'TK_CONTEXT'].map((x) => <option key={x}>{x}</option>)}</select></Field>
          <Field label="Publication date"><input type="date" className="w-full" value={m.publication_date} onChange={set('publication_date')} /></Field>
          <Field label="Effective date"><input type="date" className="w-full" value={m.effective_date} onChange={set('effective_date')} /></Field>
          <div className="md:col-span-4 flex items-center gap-3"><Button type="submit" loading={ingest.isPending} disabled={!file || !m.source_id || m.title.length < 2}>Ingest</Button><span className="text-xs text-text-muted">Runs as a background job (parsing, OCR fallback, chunking, embedding) — progress appears below.</span></div>
        </form>
        {ingest.isError && <div className="mt-2"><ErrorState error={ingest.error} /></div>}
      </Card>
      {jobs.isLoading && <Spinner />}
      {jobs.isError && <ErrorState error={jobs.error} onRetry={() => jobs.refetch()} />}
      <div className="space-y-2">
        {jobs.data?.length === 0 && <p className="text-sm text-text-muted">No ingestion jobs yet.</p>}
        {jobs.data?.map((j) => (
          <div key={j.id} className="rounded-lg border border-surface-border bg-surface-elevated p-3 text-sm">
            <div className="flex flex-wrap items-center justify-between gap-2"><span className="font-medium">{j.file_name}</span>
              <span className="flex items-center gap-2 text-xs text-text-muted">{fmtDateTime(j.created_at)} <Badge tone={j.status === 'SUCCEEDED' ? 'ok' : j.status === 'FAILED' ? 'danger' : 'info'}>{j.status}</Badge></span></div>
            {j.error && <p className="mt-1 text-xs text-danger">{j.error}</p>}
            <p className="mt-1 text-xs text-text-secondary">{j.steps.map((s: any) => s.step).join(' → ')}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
