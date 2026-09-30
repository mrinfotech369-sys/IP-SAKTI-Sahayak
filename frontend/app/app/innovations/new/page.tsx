'use client';

import { useQueryClient } from '@tanstack/react-query';
import { Plus, Trash2 } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { Button, Card, ErrorState, Field, Notice, PageHeader, ProgressSteps, cx, useStepTicker } from '@/components/ui';
import { BackLink } from '@/components/back';
import { post } from '@/lib/api';
import { useApp } from '@/lib/providers';

const STEPS = ['Basic information', 'Ingredients', 'Formulation', 'Process', 'Claims', 'Markets', 'Confidentiality'];
const EMPTY_ING = { common_name: '', sanskrit_name: '', hindi_name: '', botanical_name: '', chemical_name: '', extract: '', quantity: '', source: '' };
const CONFIDENTIAL_WARNING = 'Do not disclose unnecessary unpublished invention details. This system does not create attorney-client privilege.';

export default function NewInnovation() {
  const router = useRouter();
  const qc = useQueryClient();
  const { t } = useApp();
  const [step, setStep] = useState(0);
  const [basic, setBasic] = useState({ name: '', description: '', innovation_type: 'Formulation', intended_use: '', target_market: '', country: 'India' });
  const [ingredients, setIngredients] = useState([{ ...EMPTY_ING }]);
  const [formulation, setFormulation] = useState({ dosage_form: '', composition: '', formulation: '', delivery_mechanism: '', preparation_method: '' });
  const [process, setProcess] = useState({ extraction: '', processing: '', purification: '', manufacturing: '', novel_process: '', unique_parameters: '' });
  const [claims, setClaims] = useState<string[]>(['']);
  const [markets, setMarkets] = useState<string[]>(['IN']);
  const [confidentiality, setConfidentiality] = useState<'PUBLIC_RESEARCH' | 'INTERNAL' | 'CONFIDENTIAL'>('INTERNAL');
  const [ack, setAck] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [active, setActive] = useState(0);
  const progress = [t.loading.analyzing, t.loading.terminology, t.loading.scientific, t.loading.patents, t.loading.jurisdictions, t.loading.verifying];
  useStepTicker(busy, progress.length, setActive, 450);

  const stepError = (): string | null => {
    if (step === 0 && basic.name.trim().length < 2) return 'Innovation name is required.';
    if (step === 1 && !ingredients.some((i) => i.common_name || i.sanskrit_name || i.botanical_name)) return 'Add at least one ingredient.';
    if (step === 5 && markets.length === 0) return 'Select at least one market.';
    if (step === 6 && confidentiality === 'CONFIDENTIAL' && !ack) return 'Acknowledge the confidentiality notice to continue.';
    return null;
  };
  const blocked = stepError();

  async function submit() {
    setBusy(true);
    setErr(null);
    try {
      const inn = await post<any>('/innovations', {
        wizard: { basic, ingredients: ingredients.filter((i) => i.common_name || i.sanskrit_name || i.botanical_name), formulation, process,
          claims: claims.filter((c) => c.trim()), markets, confidentiality },
        acknowledge_confidentiality: ack,
      });
      qc.invalidateQueries({ queryKey: ['innovations'] });
      qc.invalidateQueries({ queryKey: ['dashboard'] });
      router.push(`/app/innovations/${inn.id}?created=1`);
    } catch (e) {
      setErr(e);
      setBusy(false);
    }
  }

  const upd = <T,>(setter: (v: T) => void, obj: T) => (k: keyof T) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
    setter({ ...obj, [k]: e.target.value });
  const b = upd(setBasic, basic);
  const f = upd(setFormulation, formulation);
  const p = upd(setProcess, process);

  return (
    <div>
      <div className="mb-3"><BackLink href="/app/innovations">Cancel — back to innovations</BackLink></div>
      <PageHeader eyebrow="Innovation Profiler" title={t.nav.createInnovation} subtitle="Describe the innovation. The profiler extracts structured features, normalises terminology and flags missing information — it never invents values." />
      <ol className="mb-6 flex flex-wrap gap-1" aria-label="Wizard steps">
        {STEPS.map((s, i) => (
          <li key={s}>
            <button onClick={() => i < step && setStep(i)} disabled={i > step}
              className={cx('rounded-full border px-3 py-1 text-xs', i === step ? 'border-deep-green bg-deep-green text-white' : i < step ? 'border-green/40 text-green' : 'border-surface-border text-text-muted')}
              aria-current={i === step ? 'step' : undefined}>
              {i + 1}. {s}
            </button>
          </li>
        ))}
      </ol>

      <Card>
        {step === 0 && (
          <div className="grid gap-4 md:grid-cols-2">
            <Field label="Innovation name" required><input className="w-full" value={basic.name} onChange={b('name')} /></Field>
            <Field label="Innovation type">
              <select className="w-full" value={basic.innovation_type} onChange={b('innovation_type')}>
                {['Formulation', 'Process', 'Formulation + process', 'Delivery system', 'New use', 'Other'].map((x) => <option key={x}>{x}</option>)}
              </select>
            </Field>
            <div className="md:col-span-2"><Field label="Description"><textarea className="w-full" rows={4} value={basic.description} onChange={b('description')} /></Field></div>
            <Field label="Intended use" hint="Drives regulatory classification in every market."><input className="w-full" value={basic.intended_use} onChange={b('intended_use')} /></Field>
            <Field label="Target market (free text)"><input className="w-full" value={basic.target_market} onChange={b('target_market')} /></Field>
            <Field label="Country of development"><input className="w-full" value={basic.country} onChange={b('country')} /></Field>
          </div>
        )}

        {step === 1 && (
          <div className="space-y-3">
            <p className="text-xs text-text-secondary">Common names are not assumed to map to one species — ambiguous names (e.g. Brahmi) will be flagged for confirmation.</p>
            {ingredients.map((ing, idx) => (
              <fieldset key={idx} className="rounded border border-surface-border p-3">
                <legend className="px-1 text-xs font-semibold">Ingredient {idx + 1}</legend>
                <div className="grid gap-2 md:grid-cols-4">
                  {(Object.keys(EMPTY_ING) as (keyof typeof EMPTY_ING)[]).map((k) => (
                    <Field key={k} label={k.replace('_', ' ')}>
                      <input className="w-full" value={ing[k]} onChange={(e) => setIngredients(ingredients.map((x, i) => (i === idx ? { ...x, [k]: e.target.value } : x)))} />
                    </Field>
                  ))}
                </div>
                {ingredients.length > 1 && (
                  <Button variant="ghost" size="sm" className="mt-2" onClick={() => setIngredients(ingredients.filter((_, i) => i !== idx))}><Trash2 className="h-3 w-3" /> Remove</Button>
                )}
              </fieldset>
            ))}
            <Button variant="secondary" size="sm" onClick={() => setIngredients([...ingredients, { ...EMPTY_ING }])}><Plus className="h-3 w-3" /> Add ingredient</Button>
          </div>
        )}

        {step === 2 && (
          <div className="grid gap-4 md:grid-cols-2">
            <Field label="Dosage form" hint="e.g. tablet, capsule, effervescent granules, oil"><input className="w-full" value={formulation.dosage_form} onChange={f('dosage_form')} /></Field>
            <Field label="Delivery mechanism"><input className="w-full" value={formulation.delivery_mechanism} onChange={f('delivery_mechanism')} /></Field>
            <Field label="Composition"><textarea className="w-full" rows={3} value={formulation.composition} onChange={f('composition')} /></Field>
            <Field label="Formulation"><textarea className="w-full" rows={3} value={formulation.formulation} onChange={f('formulation')} /></Field>
            <div className="md:col-span-2"><Field label="Preparation method"><textarea className="w-full" rows={2} value={formulation.preparation_method} onChange={f('preparation_method')} /></Field></div>
          </div>
        )}

        {step === 3 && (
          <div className="grid gap-4 md:grid-cols-2">
            {(Object.keys(process) as (keyof typeof process)[]).map((k) => (
              <Field key={k} label={k.replace('_', ' ')}><textarea className="w-full" rows={2} value={process[k]} onChange={p(k)} /></Field>
            ))}
          </div>
        )}

        {step === 4 && (
          <div className="space-y-3">
            <Notice tone="warn">These are user-provided proposed claims. They are not validated medical or legal claims.</Notice>
            {claims.map((c, idx) => (
              <div key={idx} className="flex gap-2">
                <input className="flex-1" value={c} placeholder="e.g. Supports a healthy stress response" aria-label={`Claim ${idx + 1}`}
                  onChange={(e) => setClaims(claims.map((x, i) => (i === idx ? e.target.value : x)))} />
                <Button variant="ghost" size="sm" onClick={() => setClaims(claims.filter((_, i) => i !== idx))} aria-label="Remove claim"><Trash2 className="h-3 w-3" /></Button>
              </div>
            ))}
            <Button variant="secondary" size="sm" onClick={() => setClaims([...claims, ''])}><Plus className="h-3 w-3" /> Add claim</Button>
          </div>
        )}

        {step === 5 && (
          <fieldset className="space-y-2">
            <legend className="label">Target markets</legend>
            {[['IN', 'India'], ['US', 'USA'], ['AU', 'Australia']].map(([k, name]) => (
              <label key={k} className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={markets.includes(k)} onChange={(e) => setMarkets(e.target.checked ? [...markets, k] : markets.filter((m) => m !== k))} />
                {name}
              </label>
            ))}
          </fieldset>
        )}

        {step === 6 && (
          <div className="space-y-3">
            <fieldset className="space-y-2">
              <legend className="label">Confidentiality</legend>
              {[['PUBLIC_RESEARCH', 'Public research'], ['INTERNAL', 'Internal'], ['CONFIDENTIAL', 'Confidential innovation']].map(([k, name]) => (
                <label key={k} className="flex items-center gap-2 text-sm">
                  <input type="radio" name="conf" checked={confidentiality === k} onChange={() => setConfidentiality(k as any)} /> {name}
                </label>
              ))}
            </fieldset>
            {confidentiality === 'CONFIDENTIAL' && (
              <div className="rounded-md border-2 border-danger bg-danger-bg p-4">
                <p className="font-semibold text-danger">Confidential innovation</p>
                <p className="mt-1 text-sm">{CONFIDENTIAL_WARNING}</p>
                <label className="mt-3 flex items-center gap-2 text-sm font-medium">
                  <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} /> I understand and will avoid unnecessary disclosure.
                </label>
              </div>
            )}
          </div>
        )}
      </Card>

      {busy && (
        <Card className="mt-4" title="Building profile and running analysis">
          <ProgressSteps steps={progress} active={active} />
        </Card>
      )}
      {err != null && <div className="mt-4"><ErrorState error={err} /></div>}

      <div className="mt-4 flex items-center justify-between">
        <Button variant="secondary" onClick={() => setStep(Math.max(0, step - 1))} disabled={step === 0 || busy}>Back</Button>
        <div className="flex items-center gap-3">
          {blocked && <span className="text-xs text-danger" role="alert">{blocked}</span>}
          {step < STEPS.length - 1 ? (
            <Button onClick={() => setStep(step + 1)} disabled={!!blocked}>Next</Button>
          ) : (
            <Button onClick={submit} disabled={!!blocked} loading={busy}>Generate profile & analyse</Button>
          )}
        </div>
      </div>
    </div>
  );
}
