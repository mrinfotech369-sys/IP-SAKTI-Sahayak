'use client';

import { useMutation } from '@tanstack/react-query';
import { useParams } from 'next/navigation';
import { FormEvent, useState } from 'react';
import { EvidenceCard, PatentCard, SearchTrace, SourceDrawer, StudyCard } from '@/components/evidence';
import { Button, Card, EmptyState, ErrorState, Notice, PageHeader, ProgressSteps, useStepTicker } from '@/components/ui';
import { post } from '@/lib/api';
import { useApp } from '@/lib/providers';
import type { Evidence } from '@/lib/types';

const KINDS: Record<string, { title: string; subtitle: string; endpoint: string; example: string; domains?: string[] }> = {
  scientific: { title: 'Scientific Evidence', subtitle: 'Search peer-reviewed and configured scientific sources. Queries expand across common, botanical, Sanskrit and chemical names.', endpoint: '/search/scientific', example: 'Ashwagandha root extract stress cortisol' },
  patents: { title: 'Patent & Prior Art', subtitle: 'Search patent literature by keywords, synonyms, botanical/chemical names and semantic similarity. Results are grouped by patent family.', endpoint: '/search/patents', example: 'curcumin phospholipid complex piperine' },
  tk: { title: 'Traditional Knowledge', subtitle: 'Public and authorised TK context, ABS and disclosure law. No restricted TKDL content is accessed or reproduced.', endpoint: '/search', example: 'traditional knowledge benefit sharing biological resource patent', domains: ['TK_ABS', 'IP'] },
  regulatory: { title: 'Regulatory Navigator', subtitle: 'Jurisdiction-specific regulatory sources. Each market is searched separately — rules are never mixed.', endpoint: '/search/regulatory', example: 'claims labelling requirements herbal supplement' },
};

export default function ResearchPage() {
  const { kind } = useParams<{ kind: string }>();
  const cfg = KINDS[kind];
  const { t } = useApp();
  const [query, setQuery] = useState(cfg?.example || '');
  const [jurs, setJurs] = useState<string[]>(kind === 'regulatory' ? ['IN', 'US', 'AU'] : []);
  const [maxTier, setMaxTier] = useState('');
  const [includeSuperseded, setIncludeSuperseded] = useState(false);
  const [dateFrom, setDateFrom] = useState('');
  const [open, setOpen] = useState<Evidence | null>(null);
  const [active, setActive] = useState(0);
  const run = useMutation({
    mutationFn: () => post<any>(cfg.endpoint, {
      query, jurisdictions: jurs, domains: cfg.domains || [], max_tier: maxTier ? Number(maxTier) : null, include_superseded: includeSuperseded,
      date_from: dateFrom || null, top_k: 10,
    }),
  });
  const steps = [t.loading.terminology, kind === 'patents' ? t.loading.patents : kind === 'scientific' ? t.loading.scientific : 'Searching configured sources…', 'Reranking…'];
  useStepTicker(run.isPending, steps.length, setActive, 250);

  if (!cfg) return <EmptyState title="Unknown research module" />;
  const submit = (e: FormEvent) => { e.preventDefault(); if (query.trim().length >= 2) run.mutate(); };
  const d = run.data;

  return (
    <div>
      <PageHeader eyebrow="Research" title={cfg.title} subtitle={cfg.subtitle} />
      {kind === 'tk' && <div className="mb-4"><Notice tone="warn" title="Access limitation">TKDL records are restricted to authorised users under access agreements. This module shows only public and authorised context. No result here does NOT establish that no traditional knowledge exists.</Notice></div>}
      <Card>
        <form onSubmit={submit} className="space-y-3">
          <div className="flex gap-2">
            <input className="flex-1" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Search query" placeholder="Search…" />
            <Button type="submit" loading={run.isPending}>Search</Button>
          </div>
          <div className="flex flex-wrap items-center gap-3 text-xs">
            {kind !== 'scientific' && (
              <fieldset className="flex items-center gap-2"><legend className="sr-only">Jurisdictions</legend>
                {['IN', 'US', 'AU'].map((j) => (
                  <label key={j} className="flex items-center gap-1"><input type="checkbox" checked={jurs.includes(j)} onChange={(e) => setJurs(e.target.checked ? [...jurs, j] : jurs.filter((x) => x !== j))} /> {j}</label>
                ))}
              </fieldset>
            )}
            <select className="py-1 text-xs" value={maxTier} onChange={(e) => setMaxTier(e.target.value)} aria-label="Source tier">
              <option value="">All tiers</option><option value="1">Tier 1 only</option><option value="2">Tier 1–2</option><option value="3">Tier 1–3</option>
            </select>
            <label className="flex items-center gap-1">From <input type="date" className="py-0.5 text-xs" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} /></label>
            <label className="flex items-center gap-1"><input type="checkbox" checked={includeSuperseded} onChange={(e) => setIncludeSuperseded(e.target.checked)} /> include superseded</label>
          </div>
        </form>
      </Card>
      <div className="mt-4 space-y-4">
        {run.isPending && <Card><ProgressSteps steps={steps} active={active} /></Card>}
        {run.isError && <ErrorState error={run.error} onRetry={() => run.mutate()} />}
        {d?.terminology?.length > 0 && (
          <p className="text-xs text-text-secondary">Terminology: {d.terminology.map((m: any) => `${m.original} → ${m.botanical || m.canonical}${m.ambiguous ? ' (ambiguous)' : ''}`).join(' · ')}</p>
        )}
        {d && kind === 'patents' && (
          <>
            <Notice tone="warn">{d.review_note}</Notice>
            {d.families.length === 0 && <EmptyState title="No patent documents matched">Try synonyms, botanical or chemical names.</EmptyState>}
            {d.families.map((f: any) => (
              <Card key={f.family_id} title={<>Family <span className="font-mono">{f.family_id}</span></>} subtitle={`${f.members.length} member(s): ${f.jurisdictions.join(', ')}`}>
                <div className="space-y-3">{f.members.map((p: any) => <PatentCard key={p.patent_id} p={p} />)}</div>
              </Card>
            ))}
            <SearchTrace trace={{ retrieval: d.trace, latency_ms: d.trace.latency_ms, pipeline: [] }} />
          </>
        )}
        {d && kind === 'scientific' && (
          <>
            <Notice tone="info">{d.notice}</Notice>
            {d.results.length === 0 && <EmptyState title="No studies matched" />}
            <div className="grid gap-3 lg:grid-cols-2">{d.results.map((r: any) => r.study ? <StudyCard key={r.chunk_id} s={{ ...r.study, review_status: r.review_status }} /> : <EvidenceCard key={r.chunk_id} e={{ ...r, n: 0, passage: r.content }} onOpen={setOpen} />)}</div>
            <SearchTrace trace={{ retrieval: d.trace, latency_ms: d.trace.latency_ms, pipeline: [] }} />
          </>
        )}
        {d && kind === 'tk' && (
          <>
            {d.results.length === 0 && <EmptyState title="No accessible evidence was found in the configured public and authorized sources.">This does NOT establish that no traditional knowledge exists.</EmptyState>}
            <div className="grid gap-3 lg:grid-cols-2">{d.results.map((r: any, i: number) => <EvidenceCard key={r.chunk_id} e={{ ...r, n: i + 1, passage: r.content }} onOpen={setOpen} />)}</div>
            <SearchTrace trace={{ retrieval: d.trace, latency_ms: d.trace.latency_ms, pipeline: [] }} />
          </>
        )}
        {d && kind === 'regulatory' && (
          <div className="grid gap-4 lg:grid-cols-3">
            {Object.entries(d.by_jurisdiction).map(([j, v]: [string, any]) => (
              <Card key={j} title={{ IN: 'India', US: 'USA', AU: 'Australia' }[j]} subtitle={`${v.results.length} source passage(s)`}>
                {v.results.length === 0 && <p className="text-sm text-text-muted">No configured source addresses this for {j}.</p>}
                <div className="space-y-2">{v.results.map((r: any, i: number) => <EvidenceCard key={r.chunk_id} e={{ ...r, n: i + 1, passage: r.content }} onOpen={setOpen} compact />)}</div>
              </Card>
            ))}
          </div>
        )}
      </div>
      <SourceDrawer evidence={open} onClose={() => setOpen(null)} />
    </div>
  );
}
