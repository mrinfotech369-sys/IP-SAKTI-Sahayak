'use client';

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useParams } from 'next/navigation';
import { useEffect, useState } from 'react';
import { Badge, Button, Card, ErrorState, Field, Notice, ProgressSteps, Spinner, TierBadge, useStepTicker } from '@/components/ui';
import { post } from '@/lib/api';
import { useInnovationData } from '@/lib/hooks';

export default function ClassificationTab() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const q = useInnovationData(id, 'classification');
  const [answers, setAnswers] = useState<Record<string, any>>({});
  const [active, setActive] = useState(0);
  useEffect(() => { if (q.data) setAnswers(q.data.answers); }, [q.data]);
  const run = useMutation({
    mutationFn: () => post(`/innovations/${id}/classification`, { answers }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['innovation', id] }),
  });
  const steps = ['Reading answers…', 'Applying jurisdiction rules…', 'Retrieving category definitions…', 'Listing facts that could change the result…'];
  useStepTicker(run.isPending, steps.length, setActive, 300);

  if (q.isLoading) return <Spinner />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const result = run.data || q.data.result;
  const set = (k: string, v: any) => setAnswers({ ...answers, [k]: v });

  return (
    <div className="grid gap-5 xl:grid-cols-[420px_1fr]">
      <Card title="Classification questionnaire" subtitle="Prefilled from the profile — correct anything that is wrong.">
        <div className="space-y-3">
          {q.data.questions.map((qq: any) => (
            <Field key={qq.key} label={qq.label}>
              {qq.type === 'select' ? (
                <select className="w-full" value={answers[qq.key] || ''} onChange={(e) => set(qq.key, e.target.value)}>
                  <option value="">—</option>
                  {qq.options.map((o: string) => <option key={o}>{o}</option>)}
                </select>
              ) : qq.type === 'multi' ? (
                <div className="flex gap-3 text-sm">
                  {qq.options.map((o: string) => (
                    <label key={o} className="flex items-center gap-1">
                      <input type="checkbox" checked={(answers.markets || []).includes(o)}
                        onChange={(e) => set('markets', e.target.checked ? [...(answers.markets || []), o] : (answers.markets || []).filter((m: string) => m !== o))} /> {o}
                    </label>
                  ))}
                </div>
              ) : qq.type === 'list' ? (
                <textarea className="w-full" rows={3} value={(answers.claims || []).join('\n')} onChange={(e) => set('claims', e.target.value.split('\n'))} />
              ) : (
                <input className="w-full" value={answers[qq.key] || ''} onChange={(e) => set(qq.key, e.target.value)} />
              )}
            </Field>
          ))}
          <Button onClick={() => run.mutate()} loading={run.isPending} className="w-full">Analyse classification</Button>
          {run.isPending && <ProgressSteps steps={steps} active={active} />}
          {run.isError && <ErrorState error={run.error} />}
        </div>
      </Card>
      <div className="space-y-4">
        <Notice tone="warn">Provisional classification only — never a legal determination. Human review is always required.</Notice>
        {result?.status === 'NEEDS_INPUT' && <Notice tone="info">{result.message}</Notice>}
        {result?.results && Object.values(result.results).map((r: any) => (
          <Card key={r.jurisdiction} title={<>{r.jurisdiction_name}: <span className="font-serif text-base">{r.provisional_category}</span></>}
            subtitle={`Provisional · confidence ${r.confidence}${r.ambiguous ? ' · ambiguous — depends on positioning' : ''}`}
            actions={<Badge tone="warn">Human review required</Badge>}>
            <div className="grid gap-4 text-xs md:grid-cols-2">
              <div>
                <div className="label">Candidate categories</div>
                <ul className="space-y-1">
                  {r.candidates.map((c: any) => (
                    <li key={c.key} className="rounded border border-surface-border p-2">
                      <div className="flex justify-between"><span className="font-semibold">{c.category}</span><span className="tabular-nums">{c.confidence}</span></div>
                      <div className="text-text-secondary">{c.why}</div>
                      {c.authority && <div className="text-text-muted">{c.authority}</div>}
                    </li>
                  ))}
                </ul>
              </div>
              <div className="space-y-3">
                <div><div className="label">Facts that could change classification</div><ul className="ml-4 list-disc">{r.facts_that_could_change.map((x: string) => <li key={x}>{x}</li>)}</ul></div>
                {r.assumptions.length > 0 && <div><div className="label">Assumptions</div><ul className="ml-4 list-disc">{r.assumptions.map((x: string) => <li key={x}>{x}</li>)}</ul></div>}
                {r.missing_questions.length > 0 && <div><div className="label">Missing questions</div><ul className="ml-4 list-disc">{r.missing_questions.map((x: string) => <li key={x}>{x}</li>)}</ul></div>}
              </div>
            </div>
            {r.evidence.length > 0 && (
              <div className="mt-3">
                <div className="label">Evidence (category definitions)</div>
                <ul className="space-y-1.5 text-xs">
                  {r.evidence.map((e: any) => (
                    <li key={e.chunk_id} className="rounded bg-surface-muted p-2">
                      <div className="flex items-center gap-1"><TierBadge tier={e.tier} /><span className="font-semibold">{e.title}</span>{e.section && <span className="text-text-muted">· {e.section}</span>}</div>
                      <p className="mt-1">{e.content.slice(0, 260)}{e.content.length > 260 ? '…' : ''}</p>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </Card>
        ))}
      </div>
    </div>
  );
}
