'use client';

import { useMutation, useQuery } from '@tanstack/react-query';
import { ChevronDown, ChevronRight, ExternalLink, Plus, ShieldAlert } from 'lucide-react';
import Link from 'next/link';
import { useState } from 'react';
import { get, post } from '@/lib/api';
import { useApp } from '@/lib/providers';
import type { Evidence } from '@/lib/types';
import {
  Badge, Button, DemoBadge, Drawer, ErrorState, FreshnessBadge, JurisdictionBadge, Spinner, TierBadge, cx, fmtDate,
} from './ui';

export function SourceMeta({ e }: { e: Partial<Evidence> & { tier: number; jurisdiction: string } }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <TierBadge tier={e.tier} />
      <JurisdictionBadge j={e.jurisdiction} />
      {e.document_type && <Badge>{e.document_type.replace(/_/g, ' ').toLowerCase()}</Badge>}
      {e.freshness && <FreshnessBadge status={e.freshness} />}
      <DemoBadge reviewStatus={e.review_status} />
      {e.injection_flag && (
        <Badge tone="danger" title="Contains instruction-like text. Treated strictly as data.">
          <ShieldAlert className="h-3 w-3" /> untrusted instructions
        </Badge>
      )}
    </div>
  );
}

export function EvidenceCard({ e, innovationId, onOpen, compact }: { e: Evidence; innovationId?: string | null; onOpen?: (e: Evidence) => void; compact?: boolean }) {
  const { t } = useApp();
  const add = useMutation({
    mutationFn: () => post(`/innovations/${innovationId}/evidence`, { chunk_id: e.chunk_id, evidence_type: domainToType(e.domain, e.document_type) }),
  });
  return (
    <article className="rounded-md border border-surface-border bg-surface p-3">
      <div className="flex items-start gap-2">
        {e.n ? <span className="mt-0.5 shrink-0 rounded bg-deep-green px-1.5 text-xs font-bold text-white">[{e.n}]</span> : null}
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-semibold leading-snug">{e.title}</h3>
          <p className="text-xs text-text-secondary">
            {e.authority}
            {e.section ? ` · ${e.section}` : ''}
            {e.effective_date ? ` · effective ${e.effective_date}` : e.publication_date ? ` · ${e.publication_date}` : ''}
          </p>
          <div className="mt-1.5">
            <SourceMeta e={e} />
          </div>
        </div>
      </div>
      <blockquote className={cx('mt-2 border-l-2 border-gold pl-2 text-[13px] text-text-main', compact && 'line-clamp-3')}>“{e.passage}”</blockquote>
      <p className="mt-2 text-[11px] text-text-muted">
        <span className="font-semibold">{t.chat.why}:</span> {e.why_retrieved} · score {e.rerank_score?.toFixed(2)}
      </p>
      <div className="mt-2 flex flex-wrap gap-2">
        {onOpen && (
          <Button size="sm" variant="secondary" onClick={() => onOpen(e)}>
            {t.chat.openSource}
          </Button>
        )}
        {innovationId && (
          <Button size="sm" variant="secondary" onClick={() => add.mutate()} loading={add.isPending} disabled={add.isSuccess}>
            <Plus className="h-3 w-3" /> {add.isSuccess ? 'Added' : t.chat.addEvidence}
          </Button>
        )}
        {add.isError && <span className="text-xs text-danger">{(add.error as Error).message}</span>}
      </div>
    </article>
  );
}

function domainToType(domain: string, docType: string) {
  if (docType === 'PATENT') return 'PATENT';
  return ({ REGULATORY: 'REGULATORY', IP: 'IP', TK_ABS: 'TK', SCIENTIFIC: 'SCIENTIFIC' } as Record<string, string>)[domain] || 'REGULATORY';
}

/** Citation drawer: source details, relevant passage, metadata, URL, why retrieved, tier. */
export function SourceDrawer({ evidence, onClose }: { evidence: Evidence | null; onClose: () => void }) {
  const doc = useQuery({
    queryKey: ['document', evidence?.document_id],
    queryFn: () => get(`/documents/${evidence!.document_id}`),
    enabled: !!evidence,
  });
  return (
    <Drawer open={!!evidence} onClose={onClose} title="Source details">
      {evidence && (
        <div className="space-y-4 text-sm">
          <div>
            <h3 className="font-serif text-xl leading-snug">{evidence.title}</h3>
            <p className="text-text-secondary">{evidence.authority}</p>
            <div className="mt-2">
              <SourceMeta e={evidence} />
            </div>
          </div>
          <div>
            <div className="label">Relevant passage {evidence.section ? `— ${evidence.section}` : ''}</div>
            <blockquote className="rounded border-l-4 border-gold bg-surface-muted p-3">{evidence.passage}</blockquote>
          </div>
          <div>
            <div className="label">Why this source?</div>
            <p>
              Ranked {evidence.n ? `#${evidence.n}` : ''} with score {evidence.rerank_score?.toFixed(2)} (relevance {evidence.relevance?.toFixed(2)}) via{' '}
              {evidence.methods?.join(' + ')} retrieval: {evidence.why_retrieved}.
            </p>
          </div>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
            {[
              ['Jurisdiction', evidence.jurisdiction],
              ['Document type', evidence.document_type],
              ['Publication', evidence.publication_date || '—'],
              ['Effective', evidence.effective_date || '—'],
              ['Version', evidence.version || '—'],
              ['Last checked', fmtDate(evidence.last_checked)],
              ['Freshness', evidence.freshness],
              ['Review status', evidence.review_status],
            ].map(([k, v]) => (
              <div key={k}>
                <dt className="text-text-muted">{k}</dt>
                <dd className="font-medium">{v}</dd>
              </div>
            ))}
          </dl>
          {evidence.url ? (
            <a className="inline-flex items-center gap-1 text-info underline" href={evidence.url} target="_blank" rel="noopener noreferrer">
              Official source <ExternalLink className="h-3 w-3" />
            </a>
          ) : (
            <p className="text-xs text-text-muted">No public URL recorded for this document.</p>
          )}
          <div>
            <div className="label">Full document ({doc.data?.chunks?.length ?? '…'} passages)</div>
            {doc.isLoading && <Spinner />}
            {doc.isError && <ErrorState error={doc.error} onRetry={() => doc.refetch()} />}
            <div className="space-y-2">
              {doc.data?.chunks?.map((c: any) => (
                <div key={c.id} className={cx('rounded border p-2 text-xs', c.id === evidence.chunk_id ? 'border-gold bg-[#FBF5E6]' : 'border-surface-border')}>
                  <div className="font-semibold text-text-secondary">{c.section || `Passage ${c.index + 1}`}</div>
                  <p>{c.content}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </Drawer>
  );
}

export function SearchTrace({ trace }: { trace: any }) {
  const [open, setOpen] = useState(false);
  const { t } = useApp();
  if (!trace) return null;
  const r = trace.retrieval;
  const find = (step: string) => trace.pipeline?.find((p: any) => p.step === step)?.result;
  return (
    <div className="rounded-md border border-surface-border bg-surface">
      <button className="flex w-full items-center gap-1 px-3 py-2 text-left text-xs font-semibold text-text-secondary" onClick={() => setOpen(!open)} aria-expanded={open}>
        {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
        {t.chat.searchTrace.toUpperCase()} · {trace.latency_ms} ms
      </button>
      {open && (
        <div className="space-y-2 border-t border-surface-border px-3 py-2 text-xs">
          <Row k="Intent" v={find('intent_detection')} />
          <Row k="Jurisdiction" v={find('jurisdiction_detection')} />
          <Row k="Language" v={find('language_detection')} />
          <Row k="Normalized terms" v={(find('terminology_normalization') || []).map((m: any) => `${m.original} → ${m.botanical || m.canonical}${m.ambiguous ? ' (ambiguous)' : ''}`).join('; ') || '—'} />
          <Row k="Expanded terms" v={(find('query_expansion') || []).join(', ') || '—'} />
          {r && (
            <>
              <Row k="Sources searched" v={`filters ${JSON.stringify(Object.fromEntries(Object.entries(r.filters).filter(([, v]) => v && (!Array.isArray(v) || v.length))))}`} />
              <Row k="Documents retrieved" v={`dense ${r.counts.dense} · BM25 ${r.counts.bm25} · metadata ${r.counts.metadata} · graph ${r.counts.graph} → merged ${r.counts.merged}`} />
              <Row k="Embedding" v={r.embedding_provider} />
              <Row k="Reranking" v={r.reranking} />
              <div>
                <div className="font-semibold text-text-secondary">Documents reranked (top 10)</div>
                <table className="mt-1 w-full">
                  <thead className="text-left text-text-muted">
                    <tr><th>Title</th><th>Methods</th><th className="text-right">Dense</th><th className="text-right">Lex</th><th className="text-right">Score</th><th /></tr>
                  </thead>
                  <tbody>
                    {r.candidates.slice(0, 10).map((c: any) => (
                      <tr key={c.chunk_id} className="border-t border-surface-border">
                        <td className="max-w-[16rem] truncate py-0.5" title={c.title}>{c.title} {c.section ? `· ${c.section}` : ''}</td>
                        <td>{c.methods.join('+')}</td>
                        <td className="text-right tabular-nums">{c.dense_score.toFixed(2)}</td>
                        <td className="text-right tabular-nums">{c.lexical_score.toFixed(2)}</td>
                        <td className="text-right tabular-nums">{c.rerank_score.toFixed(2)}</td>
                        <td className="pl-1">{r.selected.includes(c.chunk_id) ? '✓' : ''}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
          <Row k="Pipeline" v={trace.pipeline?.map((p: any) => p.step).join(' → ')} />
        </div>
      )}
    </div>
  );
}

function Row({ k, v }: { k: string; v: any }) {
  return (
    <div className="grid grid-cols-[9rem_1fr] gap-2">
      <span className="font-semibold text-text-secondary">{k}</span>
      <span className="break-words">{typeof v === 'string' ? v : JSON.stringify(v)}</span>
    </div>
  );
}

export function PatentCard({ p, onReview }: { p: any; onReview?: (status: string) => void }) {
  return (
    <article className="rounded-md border border-surface-border bg-surface p-3 text-sm">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="font-semibold leading-snug">{p.title}</h3>
          <p className="font-mono text-xs text-text-secondary">{p.publication_number} · app. {p.application_number}</p>
        </div>
        <div className="flex flex-wrap gap-1">
          <JurisdictionBadge j={p.jurisdiction} />
          <DemoBadge reviewStatus={p.review_status} />
          {p.similarity_score != null && <Badge tone="gold">similarity {Number(p.similarity_score).toFixed(2)}</Badge>}
        </div>
      </div>
      <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-xs sm:grid-cols-4">
        {[
          ['Applicant', p.applicant], ['Inventors', (p.inventors || []).join(', ')], ['Priority', p.priority_date], ['Filing', p.filing_date],
          ['Publication', p.publication_date], ['Status', p.status], ['Family', p.patent_family_id], ['CPC', (p.classification_codes || []).join(', ')],
        ].map(([k, v]) => (
          <div key={k as string}><dt className="text-text-muted">{k}</dt><dd className="font-medium">{v || '—'}</dd></div>
        ))}
      </dl>
      {p.matched_features?.length > 0 && (
        <p className="mt-2 text-xs"><span className="font-semibold">Matched features:</span> {p.matched_features.join(' · ')}</p>
      )}
      {p.relevant_passage && <blockquote className="mt-2 border-l-2 border-gold pl-2 text-[13px]">“{p.relevant_passage}”</blockquote>}
      <p className="mt-2 rounded bg-warn-bg px-2 py-1 text-xs text-warn">{p.review_note}</p>
      {onReview && (
        <div className="mt-2 flex gap-2">
          <Button size="sm" variant="secondary" onClick={() => onReview('REVIEWED_RELEVANT')}>Mark relevant</Button>
          <Button size="sm" variant="ghost" onClick={() => onReview('REVIEWED_NOT_RELEVANT')}>Not relevant</Button>
        </div>
      )}
    </article>
  );
}

export function StudyCard({ s }: { s: any }) {
  const level = s.evidence_level;
  return (
    <article className="rounded-md border border-surface-border bg-surface p-3 text-sm">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <h3 className="font-semibold leading-snug">{s.title}</h3>
        <div className="flex gap-1">
          <Badge tone={level === 'FORMULATION' ? 'ok' : level === 'SAFETY' ? 'info' : 'warn'}>
            {level === 'INGREDIENT' ? 'Ingredient evidence' : level === 'FORMULATION' ? 'Final formulation evidence' : 'Quality / safety'}
          </Badge>
          <DemoBadge reviewStatus={s.review_status} />
        </div>
      </div>
      <p className="text-xs text-text-secondary">
        {(s.authors || []).join(', ')} · {s.year} · {s.journal} {s.identifier ? `· ${s.identifier}` : ''}
      </p>
      <dl className="mt-2 grid grid-cols-1 gap-x-3 gap-y-1 text-xs sm:grid-cols-2">
        {[
          ['Study type', s.study_type], ['Population', s.population], ['Intervention', s.intervention], ['Dosage', s.dosage],
          ['Duration', s.duration], ['Outcome', s.outcome], ['Relevant ingredient(s)', (s.relevant_ingredients || s.ingredients || []).join(', ')],
        ].map(([k, v]) => (
          <div key={k as string}><dt className="text-text-muted">{k}</dt><dd>{v || '—'}</dd></div>
        ))}
      </dl>
      <p className="mt-2 text-xs"><span className="font-semibold">Limitations:</span> {s.limitations || '—'}</p>
      {s.applicability && <p className="mt-1 rounded bg-surface-muted px-2 py-1 text-xs"><span className="font-semibold">Applicability:</span> {s.applicability}</p>}
      {s.url && (
        <a href={s.url} target="_blank" rel="noopener noreferrer" className="mt-2 inline-flex items-center gap-1 text-xs text-info underline">
          Source <ExternalLink className="h-3 w-3" />
        </a>
      )}
    </article>
  );
}

export function RegulatoryCard({ entry }: { entry: any }) {
  const pw = entry.pathway;
  return (
    <article className="flex flex-col rounded-lg border border-surface-border bg-surface-elevated">
      <header className="rounded-t-lg bg-deep-green px-4 py-3 text-white">
        <div className="text-[11px] uppercase tracking-widest text-gold">{entry.country}</div>
        <div className="font-serif text-lg leading-tight">{entry.possible_pathway || 'Undetermined'}</div>
        <div className="mt-1 text-[11px] opacity-80">Provisional · confidence {entry.confidence}</div>
      </header>
      <div className="flex-1 space-y-3 p-4 text-xs">
        {pw ? (
          <>
            <div><div className="label">Authority</div>{pw.authority}</div>
            <div><div className="label">Framework</div>{pw.framework}</div>
            <div><div className="label">Requirements</div><ul className="ml-4 list-disc">{pw.requirements.map((r: string) => <li key={r}>{r}</li>)}</ul></div>
            <div><div className="label">Claims considerations</div><ul className="ml-4 list-disc">{pw.claims_considerations.map((r: string) => <li key={r}>{r}</li>)}</ul></div>
            {pw.source_document && (
              <div>
                <div className="label">Source</div>
                {pw.source_document.title} <DemoBadge reviewStatus={pw.source_document.review_status} />
                {pw.effective_date && <span className="text-text-muted"> · effective {pw.effective_date}</span>}
              </div>
            )}
            <div className="flex items-center gap-2"><span className="label mb-0">Freshness</span><FreshnessBadge status={entry.freshness} /></div>
          </>
        ) : (
          <p>No pathway could be determined from the answers.</p>
        )}
        {entry.assumptions?.length > 0 && (
          <div><div className="label">Assumptions</div><ul className="ml-4 list-disc">{entry.assumptions.map((a: string) => <li key={a}>{a}</li>)}</ul></div>
        )}
        {entry.open_questions?.length > 0 && (
          <div><div className="label">Open questions</div><ul className="ml-4 list-disc">{entry.open_questions.map((a: string) => <li key={a}>{a}</li>)}</ul></div>
        )}
        {entry.alternatives?.length > 0 && <p className="text-text-muted">Alternatives: {entry.alternatives.join(' · ')}</p>}
      </div>
      <footer className="rounded-b-lg border-t border-surface-border bg-warn-bg px-4 py-2 text-[11px] font-semibold text-warn">Human review required — not a legal determination</footer>
    </article>
  );
}

export function InnovationLink({ id, name }: { id: string; name: string }) {
  return <Link className="font-medium text-deep-green underline-offset-2 hover:underline" href={`/app/innovations/${id}`}>{name}</Link>;
}
