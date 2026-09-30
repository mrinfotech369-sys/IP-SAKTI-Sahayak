'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { FormEvent, useState } from 'react';
import {
  Badge, Button, Card, DemoBadge, Drawer, EmptyState, ErrorState, Field, FreshnessBadge, JurisdictionBadge, Notice, PageHeader,
  Spinner, Tabs, TierBadge, fmtDate, fmtDateTime,
} from '@/components/ui';
import { api, get, patch, post } from '@/lib/api';

function DocumentDetail({ id, onClose }: { id: string | null; onClose: () => void }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['admin-document', id], queryFn: () => get(`/admin/documents/${id}`), enabled: !!id });
  const review = useMutation({
    mutationFn: (body: any) => patch(`/admin/documents/${id}/review`, body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['admin-document', id] }); qc.invalidateQueries({ queryKey: ['admin-documents'] }); qc.invalidateQueries({ queryKey: ['admin-update-queue'] }); },
  });
  const reindex = useMutation({
    mutationFn: () => post(`/admin/documents/${id}/reindex`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-document', id] }),
  });
  const d: any = q.data;
  return (
    <Drawer open={!!id} onClose={onClose} title={d ? d.title : 'Document'}>
      {q.isLoading && <Spinner />}
      {q.isError && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
      {d && (
        <div className="space-y-4 text-sm">
          <div className="flex flex-wrap gap-1.5">
            <TierBadge tier={d.tier} /><JurisdictionBadge j={d.jurisdiction} /><Badge>{d.document_type}</Badge>
            <FreshnessBadge status={d.freshness} /><DemoBadge reviewStatus={d.review_status} />
            {d.workspace_private && <Badge tone="warn">workspace-private — content hidden from admin view</Badge>}
          </div>
          <dl className="grid grid-cols-2 gap-2 text-xs">
            {[['Source', d.source], ['Authority', d.authority], ['Version', d.version], ['Effective', d.effective_date],
              ['Last checked', fmtDate(d.last_checked)], ['Extraction', d.extraction.method], ['OCR confidence', d.extraction.ocr_confidence ?? 'n/a'],
              ['Indexed chunks', `${d.extraction.indexed_chunks}/${d.chunks.length}`], ['Injection-flagged', d.extraction.injection_flagged_chunks],
              ['Workspace', d.workspace || '— (global)']].map(([k, v]) => (
              <div key={k as string}><dt className="text-text-muted">{k}</dt><dd className="font-medium">{v ?? '—'}</dd></div>
            ))}
          </dl>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="secondary" onClick={() => review.mutate({ action: 'mark_checked' })} loading={review.isPending}>Mark checked</Button>
            <Button size="sm" variant="secondary" onClick={() => review.mutate({ action: 'approve' })} loading={review.isPending}>Approve (verified)</Button>
            {d.review_status !== 'REJECTED' ? (
              <Button size="sm" variant="danger" onClick={() => review.mutate({ action: 'reject' })} loading={review.isPending}>Reject (excludes from retrieval)</Button>
            ) : (
              <Button size="sm" variant="secondary" onClick={() => review.mutate({ action: 'restore' })} loading={review.isPending}>Restore</Button>
            )}
            <Button size="sm" variant="ghost" onClick={() => reindex.mutate()} loading={reindex.isPending}>Re-index (re-embed all chunks)</Button>
          </div>
          {review.isError && <ErrorState error={review.error} />}
          {reindex.isSuccess && <Notice tone="ok">Re-indexed {(reindex.data as any).reindexed_chunks} chunks with {(reindex.data as any).embedding_provider}.</Notice>}
          {d.extraction.jobs?.length > 0 && (
            <div><div className="label">Ingestion job(s)</div>
              <ul className="space-y-1 text-xs">{d.extraction.jobs.map((j: any) => <li key={j.id}>{fmtDateTime(j.created_at)} — <Badge tone={j.status === 'SUCCEEDED' ? 'ok' : 'danger'}>{j.status}</Badge> {j.steps.map((s: any) => s.step).join(' → ')}</li>)}</ul>
            </div>
          )}
          <div>
            <div className="label">Passages ({d.chunks.length})</div>
            <div className="space-y-2">
              {d.chunks.map((c: any) => (
                <div key={c.id} className="rounded border border-surface-border p-2 text-xs">
                  <div className="mb-1 flex gap-1"><span className="font-semibold">{c.section || `Passage ${c.index + 1}`}</span><Badge>{c.chunk_type?.toLowerCase()}</Badge>{c.injection_flag && <Badge tone="danger">instruction-like text</Badge>}</div>
                  {c.content !== null ? <p>{c.content}</p> : <p className="italic text-text-muted">Content hidden — workspace-private document.</p>}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </Drawer>
  );
}

function AllDocumentsTab({ onOpen }: { onOpen: (id: string) => void }) {
  const [q, setQ] = useState('');
  const [domain, setDomain] = useState('');
  const [jurisdiction, setJurisdiction] = useState('');
  const [status, setStatus] = useState('');
  const [scope, setScope] = useState('');
  const params = new URLSearchParams({ ...(q && { q }), ...(domain && { domain }), ...(jurisdiction && { jurisdiction }), ...(status && { status }), ...(scope && { scope }) }).toString();
  const docs = useQuery({ queryKey: ['admin-documents', q, domain, jurisdiction, status, scope], queryFn: () => get<any[]>(`/admin/documents${params ? `?${params}` : ''}`) });

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2 text-sm">
        <input placeholder="Search titles…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search titles" />
        <select value={domain} onChange={(e) => setDomain(e.target.value)} aria-label="Domain"><option value="">All domains</option>{['IP', 'TK_ABS', 'REGULATORY', 'SCIENTIFIC'].map((d) => <option key={d}>{d}</option>)}</select>
        <select value={jurisdiction} onChange={(e) => setJurisdiction(e.target.value)} aria-label="Jurisdiction"><option value="">All jurisdictions</option>{['IN', 'US', 'AU', 'INTERNATIONAL'].map((d) => <option key={d}>{d}</option>)}</select>
        <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Review status"><option value="">All statuses</option>{['PENDING_REVIEW', 'VERIFIED', 'REJECTED', 'SEED_SUMMARY', 'UPLOADED_OFFICIAL', 'DEMO_FICTIONAL'].map((d) => <option key={d}>{d}</option>)}</select>
        <select value={scope} onChange={(e) => setScope(e.target.value)} aria-label="Scope"><option value="">Global + workspace</option><option value="global">Global corpus only</option><option value="workspace">Workspace uploads only</option></select>
      </div>
      {docs.isLoading && <Spinner />}
      {docs.isError && <ErrorState error={docs.error} onRetry={() => docs.refetch()} />}
      {docs.data && docs.data.length === 0 && <EmptyState title="No documents match these filters" />}
      <div className="overflow-x-auto rounded-lg border border-surface-border bg-surface-elevated">
        <table className="w-full text-left text-sm">
          <thead className="bg-surface-muted text-xs text-text-secondary"><tr><th className="px-3 py-2">Title</th><th>Tier</th><th>Jurisdiction</th><th>Scope</th><th>Freshness</th><th>Status</th><th className="text-right pr-3">Indexed</th></tr></thead>
          <tbody>{docs.data?.map((d) => (
            <tr key={d.id} className="cursor-pointer border-t border-surface-border align-top hover:bg-surface-muted" onClick={() => onOpen(d.id)}>
              <td className="px-3 py-2"><div className="font-medium">{d.title}</div><div className="text-xs text-text-muted">{d.authority}</div></td>
              <td><TierBadge tier={d.tier} /></td><td><JurisdictionBadge j={d.jurisdiction} /></td>
              <td className="text-xs">{d.workspace || 'Global'}</td><td><FreshnessBadge status={d.freshness} /></td>
              <td><DemoBadge reviewStatus={d.review_status} />{d.review_status === 'VERIFIED' && <Badge tone="ok">verified</Badge>}{d.review_status === 'REJECTED' && <Badge tone="danger">rejected</Badge>}</td>
              <td className="pr-3 text-right tabular-nums">{d.indexed_chunks}/{d.chunks}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
    </div>
  );
}

function NeedsReviewTab({ onOpen }: { onOpen: (id: string) => void }) {
  const q = useQuery({ queryKey: ['admin-update-queue'], queryFn: () => get<any[]>('/admin/update-queue') });
  return (
    <div>
      {q.isLoading && <Spinner />}
      {q.isError && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
      {q.data?.length === 0 && <EmptyState title="Everything is up to date" />}
      <div className="overflow-x-auto rounded-lg border border-surface-border bg-surface-elevated">
        <table className="w-full text-left text-sm">
          <thead className="bg-surface-muted text-xs text-text-secondary"><tr><th className="px-3 py-2">Document</th><th>Status</th><th>Last checked</th><th>Frequency</th><th>Curator</th></tr></thead>
          <tbody>{q.data?.map((d) => (
            <tr key={d.document_id} className="cursor-pointer border-t border-surface-border align-top hover:bg-surface-muted" onClick={() => onOpen(d.document_id)}>
              <td className="px-3 py-2"><div className="font-medium">{d.title}</div><div className="text-xs text-text-muted">{d.source} · {d.jurisdiction} · version {d.version || '—'}</div></td>
              <td><Badge tone={d.update_status === 'Overdue' ? 'danger' : d.update_status === 'Superseded' ? 'neutral' : 'warn'}>{d.update_status}</Badge></td>
              <td className="text-xs">{fmtDate(d.last_checked)}{d.age_days != null && <div className="text-text-muted">{d.age_days} days ago</div>}</td>
              <td className="text-xs">every {d.frequency_days} days</td>
              <td className="text-xs">{d.curator}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
    </div>
  );
}

function IngestTab() {
  const qc = useQueryClient();
  const sources = useQuery({ queryKey: ['admin-sources'], queryFn: () => get<any[]>('/admin/sources') });
  const [file, setFile] = useState<File | null>(null);
  const [m, setM] = useState({ title: '', source_id: '', jurisdiction: 'IN', domain: 'REGULATORY', document_type: 'GUIDANCE', publication_date: '', effective_date: '', url: '' });
  const ingest = useMutation({
    mutationFn: () => { const fd = new FormData(); fd.append('file', file!); Object.entries(m).forEach(([k, v]) => v && fd.append(k, v)); return api('/admin/documents/ingest', { form: fd }); },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['admin-ingestion-jobs'] }); qc.invalidateQueries({ queryKey: ['admin-documents'] }); setFile(null); },
  });
  const set = (k: string) => (e: any) => setM({ ...m, [k]: e.target.value });
  return (
    <Card title="Ingest into global corpus" subtitle="validate → hash → extract → section detection → clean → structure-aware chunk → injection scan → embed → index">
      <form onSubmit={(e: FormEvent) => { e.preventDefault(); ingest.mutate(); }} className="grid gap-3 md:grid-cols-4">
        <Field label="File (PDF/TXT/MD)" required><input type="file" accept=".pdf,.txt,.md" onChange={(e) => setFile(e.target.files?.[0] || null)} /></Field>
        <Field label="Title" required><input className="w-full" value={m.title} onChange={set('title')} /></Field>
        <Field label="Source" required><select className="w-full" value={m.source_id} onChange={set('source_id')}><option value="">Select…</option>{sources.data?.map((s) => <option key={s.id} value={s.id}>{s.name} (Tier {s.authority_tier})</option>)}</select></Field>
        <Field label="Jurisdiction"><select className="w-full" value={m.jurisdiction} onChange={set('jurisdiction')}>{['IN', 'US', 'AU', 'INTERNATIONAL'].map((x) => <option key={x}>{x}</option>)}</select></Field>
        <Field label="Domain"><select className="w-full" value={m.domain} onChange={set('domain')}>{['REGULATORY', 'IP', 'TK_ABS', 'SCIENTIFIC'].map((x) => <option key={x}>{x}</option>)}</select></Field>
        <Field label="Document type"><select className="w-full" value={m.document_type} onChange={set('document_type')}>{['LEGISLATION', 'RULES', 'REGULATION', 'GUIDANCE', 'TREATY', 'STUDY', 'PATENT', 'TK_CONTEXT'].map((x) => <option key={x}>{x}</option>)}</select></Field>
        <Field label="Publication date"><input type="date" className="w-full" value={m.publication_date} onChange={set('publication_date')} /></Field>
        <Field label="Effective date"><input type="date" className="w-full" value={m.effective_date} onChange={set('effective_date')} /></Field>
        <div className="flex items-center gap-3 md:col-span-4"><Button type="submit" loading={ingest.isPending} disabled={!file || !m.source_id || m.title.length < 2}>Ingest</Button><span className="text-xs text-text-muted">Runs as a background job — check the Jobs tab for progress.</span></div>
      </form>
      {ingest.isError && <div className="mt-2"><ErrorState error={ingest.error} /></div>}
      {ingest.isSuccess && <div className="mt-2"><Notice tone="ok">Queued. See the Jobs tab.</Notice></div>}
    </Card>
  );
}

function JobsTab() {
  const jobs = useQuery({
    queryKey: ['admin-ingestion-jobs'], queryFn: () => get<any[]>('/admin/ingestion-jobs'),
    refetchInterval: (qq) => ((qq.state.data as any[] | undefined)?.some((j) => ['PENDING', 'RUNNING'].includes(j.status)) ? 1000 : false),
  });
  return (
    <div className="space-y-2">
      {jobs.isLoading && <Spinner />}
      {jobs.isError && <ErrorState error={jobs.error} onRetry={() => jobs.refetch()} />}
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
  );
}

export default function AdminDocuments() {
  const [tab, setTab] = useState('all');
  const [openId, setOpenId] = useState<string | null>(null);
  return (
    <div>
      <PageHeader eyebrow="Admin console" title="Document Management" subtitle="Upload, view, re-index and manage status for every document — global corpus and workspace uploads." />
      <Tabs tabs={[{ key: 'all', label: 'All Documents' }, { key: 'review', label: 'Needs Review' }, { key: 'ingest', label: 'Ingest New' }, { key: 'jobs', label: 'Jobs' }]} active={tab} onChange={setTab} />
      <div className="mt-4">
        {tab === 'all' && <AllDocumentsTab onOpen={setOpenId} />}
        {tab === 'review' && <NeedsReviewTab onOpen={setOpenId} />}
        {tab === 'ingest' && <IngestTab />}
        {tab === 'jobs' && <JobsTab />}
      </div>
      <DocumentDetail id={openId} onClose={() => setOpenId(null)} />
    </div>
  );
}
