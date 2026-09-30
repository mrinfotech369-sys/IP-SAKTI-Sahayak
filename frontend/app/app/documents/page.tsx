'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Link from 'next/link';
import { FormEvent, useEffect, useState } from 'react';
import { DemoBadge, Badge, Button, Card, ErrorState, Field, FreshnessBadge, JurisdictionBadge, Notice, PageHeader, Spinner, TierBadge } from '@/components/ui';
import { api, get } from '@/lib/api';

export default function Documents() {
  const qc = useQueryClient();
  const [domain, setDomain] = useState('');
  const [jur, setJur] = useState('');
  const [q, setQ] = useState('');
  const docs = useQuery({ queryKey: ['documents', domain, jur, q], queryFn: () => get<any[]>(`/documents?${new URLSearchParams({ ...(domain && { domain }), ...(jur && { jurisdiction: jur }), ...(q && { q }) })}`) });
  const [file, setFile] = useState<File | null>(null);
  const [ack, setAck] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const notice = useQuery({ queryKey: ['upload-notice'], queryFn: () => get('/uploads/notice') });
  const job = useQuery({
    queryKey: ['job', jobId], queryFn: () => get(`/ingestion-jobs/${jobId}`), enabled: !!jobId,
    refetchInterval: (qq) => (['SUCCEEDED', 'FAILED'].includes((qq.state.data as any)?.job?.status) ? false : 800),
  });
  const [meta, setMeta] = useState({ title: '', jurisdiction: 'INTERNATIONAL', domain: 'SCIENTIFIC' });
  const upload = useMutation({
    mutationFn: () => {
      const fd = new FormData();
      fd.append('file', file!);
      Object.entries(meta).forEach(([k, v]) => fd.append(k, v));
      fd.append('privacy_ack', String(ack));
      return api<any>('/documents', { form: fd });
    },
    onSuccess: (d) => { setJobId(d.job.id); setFile(null); setMeta({ ...meta, title: '' }); },
  });
  const submit = (e: FormEvent) => { e.preventDefault(); if (file && meta.title.length >= 2 && ack) upload.mutate(); };
  const jd = job.data as any;
  const jobStatus = jd?.job?.status;
  useEffect(() => {
    if (jobStatus === 'SUCCEEDED') qc.invalidateQueries({ queryKey: ['documents'] });
  }, [jobStatus, qc]);

  return (
    <div>
      <PageHeader title="Documents" subtitle="Global corpus plus documents uploaded to this workspace. Uploads are Tier 5 (unverified), workspace-private, and scanned for prompt-injection text." />
      <Card title="Upload a document" subtitle="PDF, TXT or MD · max 10 MB · file signature, embedded-script and encoding checks">
        {notice.data && (
          <div className="mb-3 rounded-md border border-info/30 bg-info-bg p-3 text-xs">
            <div className="font-semibold text-info">Before you upload — privacy & retention</div>
            <p className="mt-1">{notice.data.notice}</p>
            <p className="mt-1 text-text-secondary">Retention: {notice.data.retention_policy} · max {notice.data.max_mb} MB · OCR for scanned PDFs: {notice.data.ocr_available ? 'available (English)' : 'not installed'}</p>
            <label className="mt-2 flex items-center gap-2 font-medium"><input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} /> I have read this notice</label>
          </div>
        )}
        <form onSubmit={submit} className="grid gap-3 md:grid-cols-[2fr_1fr_1fr_auto] md:items-end">
          <Field label="File" required><input type="file" accept=".pdf,.txt,.md" onChange={(e) => setFile(e.target.files?.[0] || null)} className="w-full" /></Field>
          <Field label="Title" required><input className="w-full" value={meta.title} onChange={(e) => setMeta({ ...meta, title: e.target.value })} /></Field>
          <Field label="Domain">
            <select className="w-full" value={meta.domain} onChange={(e) => setMeta({ ...meta, domain: e.target.value })}>
              {['SCIENTIFIC', 'REGULATORY', 'IP', 'TK_ABS'].map((d) => <option key={d}>{d}</option>)}
            </select>
          </Field>
          <Button type="submit" loading={upload.isPending} disabled={!file || meta.title.length < 2 || !ack}>Upload & ingest</Button>
        </form>
        {upload.isError && <div className="mt-3"><ErrorState error={upload.error} /></div>}
        {jd && (
          <div className="mt-3"><Notice tone={jd.job.status === 'FAILED' ? 'danger' : jd.job.status === 'SUCCEEDED' ? 'ok' : 'info'} title={`Ingestion job: ${jd.job.status}`}>
            {jd.job.steps.map((s: any) => s.step).join(' → ')}
            {jd.job.error && <div className="mt-1">{jd.job.error}</div>}
            {jd.document && <div className="mt-1">Indexed “{jd.document.title}” · {jd.document.extraction_method}{jd.document.ocr_confidence != null ? ` · OCR confidence ${jd.document.ocr_confidence}` : ''} · {jd.document.review_status}</div>}
            {jd.job.steps.find((s: any) => s.injection_flagged_chunks)?.injection_flagged_chunks > 0 && <div className="mt-1">Instruction-like text was detected and will be treated as data.</div>}
          </Notice></div>
        )}
      </Card>
      <div className="my-4 flex flex-wrap gap-2 text-sm">
        <input placeholder="Search titles…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search titles" />
        <select value={domain} onChange={(e) => setDomain(e.target.value)} aria-label="Domain"><option value="">All domains</option>{['IP', 'TK_ABS', 'REGULATORY', 'SCIENTIFIC'].map((d) => <option key={d}>{d}</option>)}</select>
        <select value={jur} onChange={(e) => setJur(e.target.value)} aria-label="Jurisdiction"><option value="">All jurisdictions</option>{['IN', 'US', 'AU', 'INTERNATIONAL'].map((d) => <option key={d}>{d}</option>)}</select>
      </div>
      {docs.isLoading && <Spinner />}
      {docs.isError && <ErrorState error={docs.error} onRetry={() => docs.refetch()} />}
      <div className="overflow-x-auto rounded-lg border border-surface-border bg-surface-elevated">
        <table className="w-full text-left text-sm">
          <thead className="bg-surface-muted text-xs text-text-secondary"><tr><th className="px-3 py-2">Title</th><th>Tier</th><th>Jurisdiction</th><th>Domain</th><th>Effective</th><th>Freshness</th><th>Status</th><th className="pr-3 text-right">Chunks</th></tr></thead>
          <tbody>
            {docs.data?.map((d) => (
              <tr key={d.id} className="border-t border-surface-border align-top">
                <td className="px-3 py-2"><Link href={`/app/documents/${d.id}`} className="font-medium hover:underline">{d.title}</Link><div className="text-xs text-text-muted">{d.authority}{d.workspace_scoped ? ' · workspace upload' : ''}</div></td>
                <td><TierBadge tier={d.tier} /></td><td><JurisdictionBadge j={d.jurisdiction} /></td><td className="text-xs">{d.domain}</td>
                <td className="text-xs">{d.effective_date || d.publication_date || '—'}</td>
                <td><FreshnessBadge status={d.freshness} /></td>
                <td><DemoBadge reviewStatus={d.review_status} />{d.review_status === 'UPLOADED_OFFICIAL' && <Badge tone="ok">uploaded official</Badge>}</td>
                <td className="pr-3 text-right tabular-nums">{d.chunks}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
