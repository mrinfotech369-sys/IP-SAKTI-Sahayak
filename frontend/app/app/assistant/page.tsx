'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Copy, Flag, MessageSquarePlus, RefreshCw, Send, ShieldAlert, ThumbsDown, ThumbsUp, Trash2 } from 'lucide-react';
import { useRouter, useSearchParams } from 'next/navigation';
import { FormEvent, Suspense, useEffect, useRef, useState } from 'react';
import { EvidenceCard, SearchTrace, SourceDrawer } from '@/components/evidence';
import {
  Badge, Button, ErrorState, JurisdictionBadge, Notice, ProgressSteps, Spinner, SupportBadge, cx, fmtDateTime, useStepTicker,
} from '@/components/ui';
import { del, get, patch, post } from '@/lib/api';
import { useApp } from '@/lib/providers';
import type { ChatMessage, Evidence, InnovationCard, KeyPoint, ResearchPayload } from '@/lib/types';

const MODES = [
  ['GENERAL', 'General research'], ['INNOVATION', 'Innovation research'], ['PATENT', 'Patent research'],
  ['SCIENTIFIC', 'Scientific evidence'], ['REGULATORY', 'Regulatory research'], ['CROSS_JURISDICTION', 'Cross-jurisdiction'],
];
const EXAMPLES = [
  'What does Section 3(p) of the Indian Patents Act exclude from patentability?',
  'What label disclaimer is required for a structure/function claim on a US dietary supplement?',
  'Compare how India, USA and Australia regulate an Ayurvedic herbal product',
  'पारंपरिक ज्ञान के पेटेंट के बारे में भारत का कानून क्या कहता है?',
  'Find prior art on curcumin phospholipid complex with piperine',
  'Give me the full TKDL records for Ashwagandha formulations',
];

export default function AssistantPage() {
  return (
    <Suspense fallback={<Spinner />}>
      <Assistant />
    </Suspense>
  );
}

function Assistant() {
  const { t, lang } = useApp();
  const params = useSearchParams();
  const router = useRouter();
  const qc = useQueryClient();
  const [convId, setConvId] = useState<string | null>(params.get('c'));
  const [innovationId, setInnovationId] = useState<string>(params.get('innovation') || '');
  const [mode, setMode] = useState(params.get('innovation') ? 'INNOVATION' : 'GENERAL');
  const [jur, setJur] = useState(params.get('jur') || '');
  useEffect(() => {
    if (!params.get('jur')) {
      try { setJur(localStorage.getItem('ipsakti.jur') || ''); } catch {}
    }
  }, [params]);
  const [maxTier, setMaxTier] = useState('');
  const [text, setText] = useState('');
  const [openEv, setOpenEv] = useState<Evidence | null>(null);
  const [focus, setFocus] = useState<string | null>(null);
  const [active, setActive] = useState(0);
  const scrollRef = useRef<HTMLDivElement>(null);

  const convs = useQuery({ queryKey: ['conversations'], queryFn: () => get<any[]>('/conversations') });
  const inns = useQuery({ queryKey: ['innovations'], queryFn: () => get<InnovationCard[]>('/innovations') });
  const msgs = useQuery({ queryKey: ['messages', convId], queryFn: () => get<ChatMessage[]>(`/conversations/${convId}/messages`), enabled: !!convId });

  const send = useMutation({
    mutationFn: (message: string) =>
      post<any>('/chat', {
        message, conversation_id: convId, innovation_id: innovationId || null, language: lang, jurisdiction: jur || null, mode,
        filters: maxTier ? { max_tier: Number(maxTier) } : {},
      }),
    onSuccess: (d) => {
      setConvId(d.conversation.id);
      setFocus(d.message.id);
      router.replace(`/app/assistant?c=${d.conversation.id}${innovationId ? `&innovation=${innovationId}` : ''}`);
      qc.setQueryData(['messages', d.conversation.id], (old: ChatMessage[] | undefined) => [...(old || []), d.user_message, d.message]);
      qc.invalidateQueries({ queryKey: ['conversations'] });
    },
  });
  const steps = [t.loading.terminology, 'Hybrid retrieval (dense + BM25 + metadata + graph)…', 'Reranking & deduplicating…', 'Generating answer…', t.loading.verifying, 'Checking conflicts & freshness…'];
  useStepTicker(send.isPending, steps.length, setActive, 350);

  // Scroll only the chat pane (scrollIntoView would also scroll the page and hide the app chrome).
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
  }, [msgs.data?.length, send.isPending]);

  function submit(e?: FormEvent, override?: string) {
    e?.preventDefault();
    const m = (override ?? text).trim();
    if (!m || send.isPending) return;
    setText('');
    send.mutate(m);
  }

  const messages = msgs.data || [];
  const focused = messages.find((m) => m.id === focus) || [...messages].reverse().find((m) => m.role === 'assistant');
  const payload: ResearchPayload | undefined = focused?.payload;

  return (
    <div className="-mx-4 -my-6 grid h-[calc(100vh-49px)] grid-cols-1 overflow-hidden md:-mx-8 lg:grid-cols-[230px_1fr] xl:grid-cols-[230px_1fr_360px]">
      {/* Conversations */}
      <aside className="hidden flex-col border-r border-surface-border bg-surface lg:flex" aria-label="Conversations">
        <div className="p-3">
          <Button className="w-full" variant="secondary" onClick={() => { setConvId(null); setFocus(null); router.replace('/app/assistant'); }}>
            <MessageSquarePlus className="h-4 w-4" /> {t.chat.newChat}
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto px-2 pb-3">
          {convs.isLoading && <Spinner />}
          {convs.data?.map((c) => (
            <div key={c.id} className={cx('group flex items-center rounded', convId === c.id ? 'bg-soft-green' : 'hover:bg-surface-muted')}>
              <button className="min-w-0 flex-1 px-2 py-1.5 text-left" onClick={() => { setConvId(c.id); setFocus(null); router.replace(`/app/assistant?c=${c.id}`); }}>
                <div className="truncate text-xs font-medium">{c.title}</div>
                <div className="text-[10px] text-text-muted">{c.mode.toLowerCase()} · {fmtDateTime(c.updated_at)}</div>
              </button>
              <button className="px-1 opacity-0 group-hover:opacity-100" aria-label="Delete conversation"
                onClick={async () => { await del(`/conversations/${c.id}`); if (convId === c.id) setConvId(null); qc.invalidateQueries({ queryKey: ['conversations'] }); }}>
                <Trash2 className="h-3 w-3 text-text-muted" />
              </button>
            </div>
          ))}
        </div>
      </aside>

      {/* Chat */}
      <section className="flex min-h-0 min-w-0 flex-col">
        <div className="flex flex-wrap items-center gap-2 border-b border-surface-border bg-darkbg px-4 py-2 text-xs">
          <label className="flex items-center gap-1">{t.chat.mode}
            <select className="py-1 text-xs" value={mode} onChange={(e) => setMode(e.target.value)}>{MODES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
          </label>
          <label className="flex items-center gap-1">{t.chat.jurisdiction}
            <select className="py-1 text-xs" value={jur} onChange={(e) => setJur(e.target.value)}>
              <option value="">{t.chat.auto}</option><option value="IN">India</option><option value="US">USA</option><option value="AU">Australia</option>
            </select>
          </label>
          <label className="flex items-center gap-1">Sources
            <select className="py-1 text-xs" value={maxTier} onChange={(e) => setMaxTier(e.target.value)}>
              <option value="">All tiers</option><option value="1">Tier 1 only (official)</option><option value="2">Tier 1–2</option><option value="3">Tier 1–3 (incl. peer-reviewed)</option>
            </select>
          </label>
          <label className="flex items-center gap-1">Innovation
            <select className="max-w-[14rem] py-1 text-xs" value={innovationId} onChange={(e) => setInnovationId(e.target.value)}>
              <option value="">None</option>{inns.data?.map((i) => <option key={i.id} value={i.id}>{i.name}</option>)}
            </select>
          </label>
        </div>

        <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-4">
          {!convId && !send.isPending && (
            <div className="mx-auto max-w-2xl py-8">
              <h1 className="font-serif text-3xl">{t.nav.assistant}</h1>
              <p className="mt-2 text-sm text-text-secondary">Answers use only configured sources. Every key point is bound to a cited passage and verified; when evidence is insufficient the assistant abstains and says what is missing.</p>
              <div className="mt-6 grid gap-2 sm:grid-cols-2">
                {EXAMPLES.map((ex) => (
                  <button key={ex} onClick={() => submit(undefined, ex)} className="rounded-md border border-surface-border bg-surface-elevated p-3 text-left text-sm hover:border-green/50">{ex}</button>
                ))}
              </div>
            </div>
          )}
          {msgs.isError && <ErrorState error={msgs.error} onRetry={() => msgs.refetch()} />}
          <div className="mx-auto max-w-3xl space-y-5">
            {messages.map((m, idx) =>
              m.role === 'user' ? (
                <div key={m.id} className="flex justify-end">
                  <div className="max-w-[85%] rounded-lg bg-deep-green px-3 py-2 text-sm text-white">{m.content}</div>
                </div>
              ) : (
                <AssistantMessage key={m.id} m={m} focused={focused?.id === m.id} onFocus={() => setFocus(m.id)} onOpenEvidence={setOpenEv}
                  innovationId={innovationId || null} onReply={(r) => submit(undefined, r)}
                  onRegenerate={() => { const prev = messages[idx - 1]; if (prev?.role === 'user') submit(undefined, prev.content); }}
                  onChanged={() => qc.invalidateQueries({ queryKey: ['messages', convId] })} />
              )
            )}
            {send.isPending && (
              <div className="rounded-lg border border-surface-border bg-surface-elevated p-4"><ProgressSteps steps={steps} active={active} /></div>
            )}
            {send.isError && <ErrorState error={send.error} onRetry={() => send.variables && send.mutate(send.variables)} />}
          </div>
        </div>

        <form onSubmit={submit} className="border-t border-surface-border bg-darkbg p-3">
          <div className="mx-auto flex max-w-3xl gap-2">
            <textarea value={text} onChange={(e) => setText(e.target.value)} rows={2} className="flex-1 resize-none" placeholder={t.chat.placeholder} aria-label="Message"
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(); } }} maxLength={4000} />
            <Button type="submit" loading={send.isPending} disabled={!text.trim()}><Send className="h-4 w-4" /> {t.chat.send}</Button>
          </div>
          <p className="mx-auto mt-1 max-w-3xl text-[10px] text-text-muted">{t.boundary}</p>
        </form>
      </section>

      {/* Evidence panel */}
      <aside className="hidden overflow-y-auto border-l border-surface-border bg-surface p-3 xl:block" aria-label="Evidence panel">
        <h2 className="mb-2 text-xs font-semibold uppercase tracking-wider text-text-secondary">{t.chat.evidence}</h2>
        {!payload?.evidence?.length && <p className="text-xs text-text-muted">Evidence for the selected answer appears here.</p>}
        <div className="space-y-2">
          {payload?.evidence?.map((e) => <EvidenceCard key={e.chunk_id} e={e} innovationId={innovationId || null} onOpen={setOpenEv} compact />)}
        </div>
      </aside>
      <SourceDrawer evidence={openEv} onClose={() => setOpenEv(null)} />
    </div>
  );
}

function AssistantMessage({ m, focused, onFocus, onOpenEvidence, innovationId, onReply, onRegenerate, onChanged }: {
  m: ChatMessage; focused: boolean; onFocus: () => void; onOpenEvidence: (e: Evidence) => void; innovationId: string | null;
  onReply: (r: string) => void; onRegenerate: () => void; onChanged: () => void;
}) {
  const { t } = useApp();
  const p: ResearchPayload = m.payload;
  const [copied, setCopied] = useState(false);
  const [reporting, setReporting] = useState(false);
  const fb = useMutation({ mutationFn: (body: any) => patch(`/messages/${m.id}`, body), onSuccess: onChanged });
  const byN = Object.fromEntries((p.evidence || []).map((e) => [e.n, e]));
  const copy = async () => {
    const txt = [p.answer, ...(p.key_points || []).map((k) => `• ${k.text} ${k.citations.map((c) => `[${c}]`).join('')}`),
      ...(p.evidence || []).map((e) => `[${e.n}] ${e.title} — ${e.authority}${e.section ? `, ${e.section}` : ''}`)].join('\n');
    await navigator.clipboard.writeText(txt);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <article onClick={onFocus} className={cx('rounded-lg border bg-surface-elevated p-4', focused ? 'border-green/60' : 'border-surface-border')} lang={p.language}>
      <div className="mb-2 flex flex-wrap items-center gap-1.5 text-[11px]">
        <Badge tone={p.type === 'abstention' ? 'warn' : p.type === 'clarification' ? 'info' : p.type === 'answer_with_boundary' ? 'gold' : 'ok'}>
          {p.type === 'abstention' ? 'Abstained' : p.type === 'clarification' ? 'Needs clarification' : p.type === 'answer_with_boundary' ? 'Answer with boundary' : t.chat.answer}
        </Badge>
        <SupportBadge status={p.evidence_status} />
        <Badge title="Confidence score">confidence {p.confidence.label.toLowerCase()} {p.confidence.score ? `(${p.confidence.score})` : ''}</Badge>
        {(p.analysis?.jurisdictions || []).map((j: string) => <JurisdictionBadge key={j} j={j} />)}
        <Badge>{p.analysis?.intent?.toLowerCase().replace(/_/g, ' ')}</Badge>
        <Badge tone={p.generation.mode === 'llm' ? 'info' : 'neutral'} title={p.generation.provider}>{p.generation.mode === 'llm' ? 'LLM' : p.generation.mode}</Badge>
        {p.evidence?.some((e) => e.is_demo) && <Badge tone="warn">{t.demo}</Badge>}
        <Badge tone="info" title="Language of this answer">Answer: {LANG[p.response_language || p.language] || p.language}</Badge>
        {(p.source_languages || []).length > 0 && <Badge title="Language of the cited sources (kept in original)">Sources: {(p.source_languages || []).map((l) => LANG[l] || l).join(', ')}</Badge>}
        {p.tkdl_access && <Badge tone="warn" title={p.tkdl_access.meaning}>{p.tkdl_access.label}</Badge>}
        <span className="ml-auto text-text-muted">{fmtDateTime(m.created_at)}</span>
      </div>

      <h3 className="text-[11px] font-semibold uppercase tracking-wider text-text-secondary">{t.chat.answer}</h3>
      <p className="mt-1 whitespace-pre-line text-sm">{p.answer}</p>

      {p.suggested_replies && (
        <div className="mt-3 flex flex-wrap gap-2">{p.suggested_replies.map((r) => <Button key={r} size="sm" variant="secondary" onClick={() => onReply(r)}>{r}</Button>)}</div>
      )}

      {p.abstention && (
        <div className="mt-3 rounded-lg border-2 border-warn bg-warn-bg p-4" role="status">
        <div className="flex items-center gap-2 text-base font-semibold text-warn"><ShieldAlert className="h-5 w-5" /> Insufficient authoritative evidence — no answer given</div>
        <dl className="mt-2 grid gap-2 text-xs text-text-main">
          {([['What I searched', 'searched'], ['What I found', 'found'], ['What is missing', 'missing'], ['Why I cannot conclude', 'why'], ['Recommended next step', 'next_step']] as const).map(([k, f]) => (
            <div key={f}><dt className="font-semibold">{k}</dt><dd>{p.abstention![f]}</dd></div>
          ))}
        </dl>
        <div className="mt-3 text-xs font-semibold">Human review path: open an innovation → Escalation & Report → Flag for Human Review.</div>
        </div>
      )}

      {p.key_points?.length > 0 && (
        <>
          <h3 className="mt-4 text-[11px] font-semibold uppercase tracking-wider text-text-secondary">{t.chat.keyFindings}</h3>
          <ul className="mt-1 space-y-2">
            {p.key_points.map((k) => <KeyPointRow key={k.id} k={k} byN={byN} onOpen={onOpenEvidence} />)}
          </ul>
        </>
      )}

      {p.conflicts?.length > 0 && (
        <div className="mt-4 rounded-md border border-danger/30 bg-danger-bg p-3">
          <h3 className="text-xs font-semibold text-danger">⚠ Conflicting sources — human review recommended</h3>
          {p.conflicts.map((c: any) => (
            <div key={c.topic} className="mt-2 grid items-stretch gap-2 text-xs md:grid-cols-[1fr_auto_1fr]">
              <div className="rounded bg-white p-2"><div className="font-semibold">{c.source_a.title}</div><div>Position: {c.source_a.position}</div><div className="text-text-muted">Effective {c.source_a.effective_date || '—'}</div></div>
              <div className="self-center text-center font-bold text-danger">VS</div>
              <div className="rounded bg-white p-2"><div className="font-semibold">{c.source_b.title}</div><div>Position: {c.source_b.position}</div><div className="text-text-muted">Effective {c.source_b.effective_date || '—'}</div></div>
              <div className="md:col-span-3">Why they may differ: {c.why_they_may_differ.join('; ')}</div>
            </div>
          ))}
        </div>
      )}

      {p.evidence?.length > 0 && (
        <>
          <h3 className="mt-4 text-[11px] font-semibold uppercase tracking-wider text-text-secondary">{t.chat.evidence}</h3>
          <ol className="mt-1 space-y-1 text-xs">
            {p.evidence.map((e) => (
              <li key={e.chunk_id}>
                <button className="text-left hover:underline" onClick={(ev) => { ev.stopPropagation(); onOpenEvidence(e); }}>
                  <span className="font-bold">[{e.n}]</span> {e.title} — {e.authority} · {e.jurisdiction}{e.section ? ` · ${e.section}` : ''}
                  {e.effective_date ? ` · effective ${e.effective_date}` : e.publication_date ? ` · ${e.publication_date}` : ''} · Tier {e.tier}
                </button>
              </li>
            ))}
          </ol>
          <div className="mt-3 space-y-2 xl:hidden">
            {p.evidence.map((e) => <EvidenceCard key={e.chunk_id} e={e} innovationId={innovationId} onOpen={onOpenEvidence} compact />)}
          </div>
        </>
      )}

      {p.limitations?.length > 0 && (
        <>
          <h3 className="mt-4 text-[11px] font-semibold uppercase tracking-wider text-text-secondary">{t.chat.limitations}</h3>
          <ul className="ml-4 mt-1 list-disc text-xs text-text-secondary">{p.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
        </>
      )}
      {p.next_step && (
        <div className="mt-3"><Notice tone="info" title={t.chat.nextStep}>{p.next_step}</Notice></div>
      )}
      <ConfidenceWhy c={p.confidence} usage={p.generation?.usage} />
      <div className="mt-3"><SearchTrace trace={p.trace} /></div>

      <div className="mt-3 flex flex-wrap gap-1 border-t border-surface-border pt-2">
        <Button size="sm" variant="ghost" onClick={copy}><Copy className="h-3 w-3" /> {copied ? 'Copied' : t.chat.copy}</Button>
        <Button size="sm" variant="ghost" onClick={onRegenerate}><RefreshCw className="h-3 w-3" /> {t.chat.regenerate}</Button>
        <Button size="sm" variant="ghost" aria-pressed={m.feedback === 'up'} onClick={() => fb.mutate({ feedback: 'up' })} aria-label="Helpful"><ThumbsUp className={cx('h-3 w-3', m.feedback === 'up' && 'text-ok')} /></Button>
        <Button size="sm" variant="ghost" aria-pressed={m.feedback === 'down'} onClick={() => fb.mutate({ feedback: 'down' })} aria-label="Not helpful"><ThumbsDown className={cx('h-3 w-3', m.feedback === 'down' && 'text-danger')} /></Button>
        <Button size="sm" variant="ghost" onClick={() => setReporting(true)}><Flag className={cx('h-3 w-3', m.flagged && 'text-danger')} /> {m.flagged ? 'Reported — report again' : 'Report issue'}</Button>
      </div>
      {reporting && <ReportIssue m={m} onDone={() => { setReporting(false); onChanged(); }} />}
    </article>
  );
}

function KeyPointRow({ k, byN, onOpen }: { k: KeyPoint; byN: Record<number, Evidence>; onOpen: (e: Evidence) => void }) {
  const [open, setOpen] = useState(false);
  const flagged = k.status === 'UNSUPPORTED' || k.status === 'CONFLICTING';
  return (
    <li className={cx('rounded-md border p-2 text-sm', flagged ? 'border-danger/40 bg-danger-bg' : 'border-surface-border')}>
      <div className="flex flex-wrap items-start gap-2">
        <span className="flex-1">
          {k.text}{' '}
          {k.citations.map((c) => (
            <button key={c} className="mx-0.5 rounded bg-deep-green px-1 text-[10px] font-bold text-white hover:bg-green" onClick={(e) => { e.stopPropagation(); byN[c] && onOpen(byN[c]); }}
              aria-label={`Open citation ${c}`}>[{c}]</button>
          ))}
        </span>
        <Badge tone={k.type === 'FACT' ? 'neutral' : k.type === 'INFERENCE' ? 'info' : 'gold'}>{k.type.replace('_', ' ').toLowerCase()}</Badge>
        <SupportBadge status={k.status} />
        <button className="text-[10px] text-text-muted underline" onClick={(e) => { e.stopPropagation(); setOpen(!open); }} aria-expanded={open}>checks</button>
      </div>
      {k.text_en && <div className="mt-1 text-[11px] text-text-muted">Verified as (English): {k.text_en}</div>}
      {open && (
        <div className="mt-2 rounded bg-surface-muted p-2 text-[11px]">
          <div>verification score {k.score} · term coverage {k.checks.term_coverage ?? '—'} · semantic {k.checks.semantic_similarity ?? '—'} · jurisdiction ok {String(k.checks.jurisdiction_ok ?? '—')} · freshness {k.checks.freshness ?? '—'}{k.checks.llm_entailment ? ` · entailment ${k.checks.llm_entailment}` : ''}</div>
          {k.notes.length > 0 && <ul className="ml-4 list-disc">{k.notes.map((n) => <li key={n}>{n}</li>)}</ul>}
        </div>
      )}
    </li>
  );
}

const LANG: Record<string, string> = { en: 'English', hi: 'हिन्दी' };

function ConfidenceWhy({ c, usage }: { c: any; usage?: any }) {
  const [open, setOpen] = useState(false);
  if (!c) return null;
  return (
    <div className="mt-3 rounded-md border border-surface-border bg-surface text-xs">
      <button className="w-full px-3 py-2 text-left font-semibold text-text-secondary" onClick={(e) => { e.stopPropagation(); setOpen(!open); }} aria-expanded={open}>
        {open ? '▾' : '▸'} Why this confidence? · {c.label.toLowerCase()} {c.score ? `(${c.score})` : ''} · heuristic, not calibrated
      </button>
      {open && (
        <div className="border-t border-surface-border px-3 py-2">
          <p className="text-text-secondary">{c.explanation}</p>
          {c.signals?.length > 0 && (
            <table className="mt-2 w-full">
              <thead className="text-left text-text-muted"><tr><th>Signal</th><th className="text-right">Value</th><th className="text-right">Weight</th></tr></thead>
              <tbody>{c.signals.map((s: any) => (
                <tr key={s.signal} className="border-t border-surface-border"><td className="py-0.5">{s.signal}</td><td className="text-right tabular-nums">{s.value}</td><td className="text-right tabular-nums">{s.weight}</td></tr>
              ))}</tbody>
            </table>
          )}
          {c.penalties?.length > 0 && <p className="mt-1 text-warn">Penalties: {c.penalties.join('; ')}</p>}
          {usage && usage.calls > 0 && <p className="mt-1 text-text-muted">LLM usage: {usage.calls} call(s), {usage.prompt_tokens + usage.completion_tokens} tokens, ≈ ${usage.estimated_cost_usd}</p>}
        </div>
      )}
    </div>
  );
}

function ReportIssue({ m, onDone }: { m: ChatMessage; onDone: () => void }) {
  const [category, setCategory] = useState('WRONG_ANSWER');
  const [reason, setReason] = useState('');
  const [kp, setKp] = useState('');
  const send = useMutation({
    mutationFn: () => post('/feedback', { message_id: m.id, category, reason, target: kp ? { key_point_id: Number(kp) } : {} }),
    onSuccess: onDone,
  });
  const p: ResearchPayload = m.payload;
  return (
    <form className="mt-2 space-y-2 rounded-md border border-danger/30 bg-danger-bg p-3 text-xs" onClick={(e) => e.stopPropagation()}
      onSubmit={(e) => { e.preventDefault(); if (reason.trim().length >= 3) send.mutate(); }}>
      <div className="font-semibold text-danger">Report an issue with this answer</div>
      <div className="flex flex-wrap gap-2">
        <select value={category} onChange={(e) => setCategory(e.target.value)} aria-label="Issue type" className="py-1 text-xs">
          <option value="WRONG_ANSWER">Wrong answer</option><option value="WRONG_SOURCE">Wrong / irrelevant source</option>
          <option value="CITATION_NOT_SUPPORTING">Citation doesn't support the claim</option><option value="OUTDATED_SOURCE">Outdated source</option>
          <option value="UNSAFE">Unsafe / out of bounds</option><option value="OTHER">Other</option>
        </select>
        <select value={kp} onChange={(e) => setKp(e.target.value)} aria-label="Key point" className="py-1 text-xs">
          <option value="">Whole answer</option>{(p.key_points || []).map((k) => <option key={k.id} value={k.id}>Key point {k.id}</option>)}
        </select>
      </div>
      <textarea className="w-full" rows={2} placeholder="What is wrong? (required)" value={reason} onChange={(e) => setReason(e.target.value)} aria-label="Reason" />
      <p className="text-text-muted">A snapshot of this answer and its source versions is saved with your report for review.</p>
      <div className="flex gap-2"><Button size="sm" type="submit" loading={send.isPending} disabled={reason.trim().length < 3}>Submit report</Button>
        <Button size="sm" variant="ghost" type="button" onClick={onDone}>Cancel</Button></div>
      {send.isError && <p className="text-danger">{(send.error as Error).message}</p>}
    </form>
  );
}
