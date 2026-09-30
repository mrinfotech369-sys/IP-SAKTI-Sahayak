'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Badge, Button, Card, ErrorState, Notice, PageHeader, ProgressSteps, Spinner, Stat, fmtDateTime, useStepTicker } from '@/components/ui';
import { get, post } from '@/lib/api';

const METRICS: [string, string][] = [
  ['test_set_size', 'Test-set size'], ['recall_at_k', 'Recall@6'], ['retrieval_precision', 'Precision@k'], ['retrieval_recall', 'Relevant-source hit rate'], ['ndcg', 'nDCG'], ['citation_correctness', 'Citation correctness'],
  ['citation_entailment', 'Citation entailment'], ['unsupported_claim_rate', 'Unsupported claim rate'], ['abstention_accuracy', 'Abstention accuracy'],
  ['jurisdiction_accuracy', 'Jurisdiction accuracy'], ['jurisdiction_contamination', 'Cross-jurisdiction contamination'], ['freshness', 'Freshness'], ['latency_p50_ms', 'Latency p50 (ms)'], ['latency_p95_ms', 'Latency p95 (ms)'],
];

export default function Evaluation() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['admin-evaluations'], queryFn: () => get('/admin/evaluations') });
  const run = useMutation({ mutationFn: () => post('/admin/evaluations/run'), onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-evaluations'] }) });
  const [active, setActive] = useState(0);
  useStepTicker(run.isPending, 3, setActive, 600);
  const latest: any = run.data || (q.data as any)?.latest;
  return (
    <div className="space-y-5">
      <PageHeader eyebrow="Admin console" title="RAG Evaluation" subtitle="Runs the seeded evaluation set through the live pipeline. Every number is computed from actual outputs — nothing is hardcoded."
        actions={<Button onClick={() => run.mutate()} loading={run.isPending}>Run evaluation</Button>} />
      {run.isPending && <Card><ProgressSteps steps={['Running the question set through the pipeline and baselines…', 'Scoring retrieval & citations…', 'Computing metrics…']} active={active} /></Card>}
      {run.isError && <ErrorState error={run.error} />}
      {q.isLoading && <Spinner />}
      {!latest && q.data && <Notice tone="info">No evaluation has been run yet. Click "Run evaluation".</Notice>}
      {latest && (
        <>
          <p className="text-xs text-text-muted">Run {fmtDateTime(latest.created_at)} · LLM {latest.llm_provider} · embeddings {latest.embedding_provider} · passed {latest.metrics.passed}/{latest.metrics.questions}</p>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
            {METRICS.map(([k, l]) => <Stat key={k} label={l} value={latest.metrics[k] ?? '—'} />)}
          </div>
          {latest.metrics.baselines && (
            <Card title="Baseline comparison (same questions, same corpus)">
              <table className="w-full text-left text-xs">
                <thead className="text-text-secondary"><tr><th className="py-1">System</th><th>Recall@6</th><th>Abstention accuracy</th><th>Cross-jurisdiction contamination</th><th>Citation verification</th></tr></thead>
                <tbody>
                  <tr className="border-t border-surface-border font-semibold"><td className="py-1.5">IP-SAKTI (hybrid RAG + verification + safety gate)</td><td>{latest.metrics.recall_at_k}</td><td>{latest.metrics.abstention_accuracy}</td><td>{latest.metrics.jurisdiction_contamination}</td><td>{latest.metrics.citation_entailment} supported</td></tr>
                  {Object.entries(latest.metrics.baselines).map(([k, b]: [string, any]) => (
                    <tr key={k} className="border-t border-surface-border"><td className="py-1.5">{k.replace(/_/g, ' ')}<div className="text-text-muted">{b.description}</div></td>
                      <td>{b.recall_at_k ?? '—'}</td><td>{b.abstention_accuracy ?? '—'}</td><td>{b.jurisdiction_contamination ?? '—'}</td><td>{b.citation_verification ?? (b.answers_with_verifiable_citations != null ? `${b.answers_with_verifiable_citations} verifiable` : '—')}</td></tr>
                  ))}
                </tbody>
              </table>
            </Card>
          )}
          {latest.metrics.classification && (
            <Card title={`Classification agreement: ${latest.metrics.classification.agreement} on ${latest.metrics.classification.labels} labels (${latest.metrics.classification.cases} cases)`} subtitle={latest.metrics.classification.note}>
              <div className="flex flex-wrap gap-1 text-xs">{latest.metrics.classification.rows.map((r: any) => (
                <Badge key={r.case + r.jurisdiction} tone={r.agree ? 'ok' : 'danger'} title={`expected ${r.expected}, predicted ${r.predicted}`}>{r.case}·{r.jurisdiction} {r.agree ? '✓' : `✕ ${r.predicted}`}</Badge>
              ))}</div>
            </Card>
          )}
          <Card title="Per-question results">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="text-text-secondary"><tr><th className="py-1">Key</th><th>Category</th><th>Question</th><th>Outcome</th><th>Abstention</th><th>P@k</th><th>Supported</th><th>Jurisdiction</th><th className="text-right">ms</th></tr></thead>
                <tbody>{latest.results.map((r: any) => (
                  <tr key={r.key} className="border-t border-surface-border align-top">
                    <td className="py-1.5 font-mono">{r.key}</td><td>{r.category.toLowerCase().replace(/_/g, ' ')}</td><td className="max-w-xs">{r.question}</td>
                    <td><Badge>{r.type}</Badge></td>
                    <td><Badge tone={r.abstention_correct ? 'ok' : 'danger'}>{r.abstention_correct ? 'correct' : 'wrong'}</Badge></td>
                    <td>{r.precision_at_k ?? '—'}</td><td>{r.supported_fraction ?? '—'}</td>
                    <td>{r.jurisdiction_correct == null ? '—' : <Badge tone={r.jurisdiction_correct ? 'ok' : 'danger'}>{String(r.jurisdiction_correct)}</Badge>}</td>
                    <td className="text-right tabular-nums">{r.latency_ms}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          </Card>
        </>
      )}
      {(q.data as any)?.history?.length > 1 && (
        <Card title="History"><ul className="space-y-1 text-xs">{(q.data as any).history.map((h: any) => <li key={h.id}>{fmtDateTime(h.created_at)} — passed {h.metrics.passed}/{h.metrics.questions} · abstention {h.metrics.abstention_accuracy} · entailment {h.metrics.citation_entailment}</li>)}</ul></Card>
      )}
    </div>
  );
}
