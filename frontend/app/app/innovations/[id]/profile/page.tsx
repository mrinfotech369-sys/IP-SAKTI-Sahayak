'use client';

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { CheckCircle2, Pencil } from 'lucide-react';
import { useParams, useSearchParams } from 'next/navigation';
import { useEffect, useState } from 'react';
import { Badge, Button, Card, ErrorState, Field, Notice, cx } from '@/components/ui';
import { patch, post } from '@/lib/api';
import { useInnovation } from '@/lib/hooks';

const FIELDS: [string, string][] = [
  ['dosage_form', 'Dosage form'], ['route', 'Route'], ['intended_use', 'Intended use'], ['composition', 'Composition'],
  ['extraction_method', 'Extraction method'], ['process', 'Process'], ['manufacturing_location', 'Manufacturing location'],
];

export default function ProfileTab() {
  const { id } = useParams<{ id: string }>();
  const created = useSearchParams().get('created');
  const qc = useQueryClient();
  const inn = useInnovation(id);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Record<string, any>>({});
  const p = inn.data?.profile;
  useEffect(() => {
    if (p) setDraft({ ...p, claims_text: (p.claims || []).join('\n') });
  }, [p]);

  const save = useMutation({
    mutationFn: (confirmOnly: boolean) =>
      patch(`/innovations/${id}/profile`, confirmOnly ? { confirm: true } : {
        ...Object.fromEntries(FIELDS.map(([k]) => [k, draft[k] || null])),
        claims: String(draft.claims_text || '').split('\n').map((s: string) => s.trim()).filter(Boolean),
        confirm: true,
      }),
    onSuccess: () => {
      setEditing(false);
      qc.invalidateQueries({ queryKey: ['innovation', id] });
    },
  });
  const regen = useMutation({ mutationFn: () => post(`/innovations/${id}/profile/generate`), onSuccess: () => qc.invalidateQueries({ queryKey: ['innovation', id] }) });

  if (!inn.data) return null;
  if (!p) {
    return (
      <Card title="Profile not generated">
        <Button onClick={() => regen.mutate()} loading={regen.isPending}>Generate profile</Button>
        {regen.isError && <ErrorState error={regen.error} />}
      </Card>
    );
  }

  return (
    <div className="space-y-5">
      {created && <Notice tone="ok" title="Innovation created">Profile generated and first analysis complete. Review the extracted profile below and confirm it — items marked “Needs confirmation” were inferred.</Notice>}
      <div className="grid gap-5 lg:grid-cols-[1.4fr_1fr]">
        <Card
          title="Structured innovation profile"
          subtitle={`Extraction: ${p.extraction_method_used} · ${p.user_confirmed ? 'confirmed by user' : 'not yet confirmed'}`}
          actions={
            editing ? (
              <>
                <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>Cancel</Button>
                <Button size="sm" onClick={() => save.mutate(false)} loading={save.isPending}>Save & confirm</Button>
              </>
            ) : (
              <>
                <Button size="sm" variant="secondary" onClick={() => setEditing(true)}><Pencil className="h-3 w-3" /> Edit</Button>
                {!p.user_confirmed && <Button size="sm" onClick={() => save.mutate(true)} loading={save.isPending}><CheckCircle2 className="h-3 w-3" /> Confirm profile</Button>}
              </>
            )
          }
        >
          {save.isError && <ErrorState error={save.error} />}
          <dl className="grid gap-3 sm:grid-cols-2">
            {FIELDS.map(([k, label]) => (
              <div key={k}>
                <dt className="label">{label}</dt>
                {editing ? (
                  <textarea rows={2} className="w-full" value={draft[k] || ''} onChange={(e) => setDraft({ ...draft, [k]: e.target.value })} aria-label={label} />
                ) : (
                  <dd className={cx('text-sm', !p[k] && 'italic text-text-muted')}>{p[k] || 'Not provided'}</dd>
                )}
              </div>
            ))}
            <div className="sm:col-span-2">
              <dt className="label">Proposed claims (user-provided — not validated medical or legal claims)</dt>
              {editing ? (
                <textarea rows={3} className="w-full" value={draft.claims_text} onChange={(e) => setDraft({ ...draft, claims_text: e.target.value })} aria-label="Claims, one per line" />
              ) : (
                <ul className="ml-4 list-disc text-sm">{(p.claims || []).map((c: string) => <li key={c}>{c}</li>)}</ul>
              )}
            </div>
            <div className="sm:col-span-2">
              <dt className="label">Target markets</dt>
              <dd className="text-sm">{(p.target_market || []).join(', ') || '—'}</dd>
            </div>
          </dl>
        </Card>

        <div className="space-y-4">
          <Card title="Missing information" subtitle="Never silently invented">
            {p.missing_information?.length ? <ul className="ml-4 list-disc space-y-1 text-sm">{p.missing_information.map((m: string) => <li key={m}>{m}</li>)}</ul> : <p className="text-sm text-text-muted">None detected.</p>}
          </Card>
          <Card title="Ambiguities">
            {p.ambiguities?.length ? <ul className="space-y-2 text-sm">{p.ambiguities.map((m: string) => <li key={m} className="rounded bg-warn-bg px-2 py-1 text-warn">{m}</li>)}</ul> : <p className="text-sm text-text-muted">None detected.</p>}
          </Card>
          <Card title="Assumptions">
            {p.assumptions?.length ? <ul className="ml-4 list-disc space-y-1 text-sm">{p.assumptions.map((m: string) => <li key={m}>{m}</li>)}</ul> : <p className="text-sm text-text-muted">None.</p>}
          </Card>
        </div>
      </div>

      <Card title="Ingredients & terminology normalisation" subtitle="Sanskrit / Hindi / English / botanical / chemical mapping. Ambiguous common names are not mapped to a single species.">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="text-text-muted">
              <tr><th className="py-1">Ingredient</th><th>Sanskrit</th><th>Hindi</th><th>Botanical</th><th>Chemical</th><th>Extract / part</th><th>Qty</th><th>Status</th></tr>
            </thead>
            <tbody>
              {p.ingredients.map((i: any) => (
                <tr key={i.name} className="border-t border-surface-border align-top">
                  <td className="py-1.5 font-medium">{i.name}</td>
                  <td>{i.sanskrit_name || '—'}</td>
                  <td>{i.hindi_name || '—'}</td>
                  <td className="italic">{i.botanical_name || i.normalized || <span className="not-italic text-danger">not confirmed</span>}</td>
                  <td>{i.chemical_name || '—'}</td>
                  <td>{i.extract || '—'}</td>
                  <td>{i.quantity || '—'}</td>
                  <td><Badge tone={i.status === 'USER_PROVIDED' ? 'ok' : 'warn'}>{i.status === 'USER_PROVIDED' ? 'User provided' : 'Needs confirmation'}</Badge></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {p.terminology?.length > 0 && (
          <div className="mt-4 overflow-x-auto">
            <div className="label">Terminology engine</div>
            <table className="w-full text-left text-xs">
              <thead className="text-text-muted"><tr><th className="py-1">Original</th><th>Normalized</th><th>Alternatives</th><th>Ambiguity</th><th>Selected meaning</th><th>Reason</th></tr></thead>
              <tbody>
                {p.terminology.map((m: any) => (
                  <tr key={m.canonical} className="border-t border-surface-border align-top">
                    <td className="py-1.5">{m.original}</td>
                    <td className="italic">{m.botanical || m.canonical}</td>
                    <td>{[m.english, ...(m.alternatives || [])].filter(Boolean).slice(0, 4).join(', ')}</td>
                    <td>{m.ambiguous ? <span className="text-danger">{m.candidate_species.join(' / ')}</span> : '—'}</td>
                    <td>{m.selected_meaning || <Badge tone="warn">Needs confirmation</Badge>}</td>
                    <td className="text-text-secondary">{m.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card title={`Technical features (${inn.data.features.length})`} subtitle="Used for patent matching, evidence discovery and the evidence graph.">
        <div className="grid gap-2 md:grid-cols-2">
          {inn.data.features.map((f) => (
            <div key={f.id} className="rounded border border-surface-border p-2 text-sm">
              <div className="flex items-center gap-2">
                <Badge tone="info">{f.feature_type}</Badge>
                {f.source === 'AI_EXTRACTED' && <Badge tone="warn">AI-extracted · confirm</Badge>}
                <span className="font-medium">{f.name}</span>
              </div>
              {f.normalized_term && <div className="mt-1 text-xs italic text-text-secondary">→ {f.normalized_term}</div>}
            </div>
          ))}
        </div>
        {p.search_terms?.length > 0 && <p className="mt-3 text-xs text-text-secondary"><span className="font-semibold">Search terms:</span> {p.search_terms.join(' · ')}</p>}
      </Card>
    </div>
  );
}
