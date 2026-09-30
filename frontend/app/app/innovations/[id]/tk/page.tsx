'use client';

import { useParams } from 'next/navigation';
import { useState } from 'react';
import { EvidenceCard, SourceDrawer } from '@/components/evidence';
import { Card, ErrorState, LinkButton, Notice, Spinner } from '@/components/ui';
import { useInnovationData } from '@/lib/hooks';
import type { Evidence } from '@/lib/types';

export default function TKTab() {
  const { id } = useParams<{ id: string }>();
  const q = useInnovationData(id, 'tk');
  const [open, setOpen] = useState<Evidence | null>(null);
  if (q.isLoading) return <Spinner label="Searching public and authorised TK sources…" />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const d = q.data;
  return (
    <div className="space-y-5">
      <div className="grid gap-3 md:grid-cols-2">
        <div className="rounded-lg border-2 border-warn bg-warn-bg p-4">
          <div className="text-xs font-semibold uppercase tracking-wider text-warn">Restricted source</div>
          <div className="mt-1 text-lg font-semibold">{d.tkdl_access.label}</div>
          <p className="mt-1 text-sm">{d.tkdl_access.meaning}</p>
          <p className="mt-1 text-xs text-text-secondary">{d.access_limitation}</p>
        </div>
        <div className="rounded-lg border-2 border-ok/40 bg-ok-bg p-4">
          <div className="text-xs font-semibold uppercase tracking-wider text-ok">Public & authorised sources — searched</div>
          <div className="mt-1 text-lg font-semibold">{d.context.length} relevant passage(s) found</div>
          <p className="mt-1 text-sm">{d.public_tk_sources_searched.length ? d.public_tk_sources_searched.join(' · ') : 'No relevant result in configured public sources.'}</p>
        </div>
      </div>
      <div className="grid gap-5 lg:grid-cols-2">
        <Card title="Traditional knowledge records">
          <p className="text-sm">{d.tk_notice}</p>
        </Card>
        <Card title="Possible overlap with documented TK">
          {d.possible_overlap.length ? <ul className="ml-4 list-disc space-y-1 text-sm">{d.possible_overlap.map((o: string) => <li key={o}>{o}</li>)}</ul> : <p className="text-sm text-text-muted">No classical ingredients recognised.</p>}
        </Card>
        <Card title="Attribution & benefit sharing"><p className="text-sm">{d.attribution}</p></Card>
        <Card title="Human escalation" actions={<LinkButton href={`/app/innovations/${id}/review`} variant="secondary">Request review</LinkButton>}>
          <p className="text-sm">{d.human_escalation}</p>
        </Card>
      </div>
      <Card title="Terminology mapping">
        <table className="w-full text-left text-xs">
          <thead className="text-text-muted"><tr><th className="py-1">Term</th><th>Sanskrit</th><th>Hindi</th><th>Botanical</th><th>Ambiguity</th></tr></thead>
          <tbody>
            {d.terminology.map((m: any) => (
              <tr key={m.canonical} className="border-t border-surface-border">
                <td className="py-1.5">{m.canonical}</td><td>{m.sanskrit || '—'}</td><td>{m.hindi || '—'}</td><td className="italic">{m.botanical || '—'}</td>
                <td>{m.ambiguous ? m.candidate_species.join(' / ') : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      <Card title="Public & authorised context (IP / ABS law)">
        <div className="grid gap-3 lg:grid-cols-2">
          {d.context.map((c: any, i: number) => <EvidenceCard key={c.chunk_id} e={{ ...c, n: i + 1, passage: c.content }} innovationId={id} onOpen={setOpen} compact />)}
        </div>
      </Card>
      <SourceDrawer evidence={open} onClose={() => setOpen(null)} />
    </div>
  );
}
