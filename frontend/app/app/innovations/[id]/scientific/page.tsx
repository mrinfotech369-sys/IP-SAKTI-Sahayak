'use client';

import { useParams } from 'next/navigation';
import { StudyCard } from '@/components/evidence';
import { Card, EmptyState, ErrorState, Notice, Spinner } from '@/components/ui';
import { useInnovationData } from '@/lib/hooks';

export default function ScientificTab() {
  const { id } = useParams<{ id: string }>();
  const q = useInnovationData(id, 'scientific');
  if (q.isLoading) return <Spinner label="Searching scientific sources…" />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const d = q.data;
  const ing = d.cards.filter((c: any) => c.evidence_level === 'INGREDIENT');
  const form = d.cards.filter((c: any) => c.evidence_level === 'FORMULATION');
  const safety = d.cards.filter((c: any) => c.evidence_level === 'SAFETY');
  return (
    <div className="space-y-5">
      <Notice tone="info">{d.notice}</Notice>
      <Card title={`Final formulation evidence (${form.length})`}>
        {form.length ? <div className="grid gap-3 lg:grid-cols-2">{form.map((s: any) => <StudyCard key={s.id} s={s} />)}</div> : (
          <EmptyState title="No evidence on this finished formulation">
            Ingredient studies below do not transfer to the final product (different extract, dose, combination and process). This is recorded as an evidence gap.
          </EmptyState>
        )}
      </Card>
      <Card title={`Ingredient evidence (${ing.length})`} subtitle={d.ingredients_without_evidence.length ? `No configured studies for: ${d.ingredients_without_evidence.join(', ')}` : undefined}>
        <div className="grid gap-3 lg:grid-cols-2">{ing.map((s: any) => <StudyCard key={s.id} s={s} />)}</div>
      </Card>
      {safety.length > 0 && (
        <Card title="Quality & safety context">
          <div className="grid gap-3 lg:grid-cols-2">{safety.map((s: any) => <StudyCard key={s.id} s={s} />)}</div>
        </Card>
      )}
    </div>
  );
}
