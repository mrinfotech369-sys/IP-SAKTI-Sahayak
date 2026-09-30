'use client';

import { useQuery } from '@tanstack/react-query';
import { Badge, Card, ErrorState, PageHeader, Spinner, Stat } from '@/components/ui';
import { get } from '@/lib/api';

const TONE: Record<string, any> = { Built: 'ok', Partial: 'warn', Planned: 'danger', 'N/A': 'neutral' };

export default function Coverage() {
  const q = useQuery({ queryKey: ['coverage'], queryFn: () => get('/coverage') });
  if (q.isLoading) return <Spinner />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const d = q.data;
  return (
    <div className="space-y-5">
      <PageHeader title="Jurisdiction & Source Coverage" subtitle="Computed live from the ingested corpus — the system only claims what is actually ingested. Planned cells are refused rather than answered." />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <Stat label="Documents" value={d.corpus.documents} /><Stat label="Chunks (passages)" value={d.corpus.chunks} />
        <Stat label="Sources" value={d.corpus.sources} /><Stat label="Real documents" value={d.corpus.real_documents} hint="seed summaries of real instruments / studies" />
        <Stat label="Demo / fictional" value={d.corpus.demo_documents} hint="patents & conflict demo" />
      </div>
      <Card title="Coverage matrix">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-surface-muted text-text-secondary"><tr><th className="px-2 py-2">Jurisdiction</th>{d.domains.map((x: any) => <th key={x.key} className="px-2">{x.name}</th>)}</tr></thead>
            <tbody>{d.matrix.map((row: any) => (
              <tr key={row.jurisdiction} className="border-t border-surface-border align-top">
                <th scope="row" className="px-2 py-2 text-sm">{row.name}</th>
                {d.domains.map((x: any) => {
                  const c = row.cells[x.key];
                  return (
                    <td key={x.key} className="px-2 py-2">
                      <Badge tone={TONE[c.status]}>{c.status}</Badge>
                      {c.status !== 'N/A' && <div className="mt-1 text-text-muted">{c.documents} docs · {c.chunks} chunks{c.demo ? ` · ${c.demo} demo` : ''}</div>}
                      {c.note && <div className="mt-1 text-warn">{c.note}</div>}
                      {c.titles.length > 0 && (
                        <details className="mt-1"><summary className="cursor-pointer text-info">documents</summary>
                          <ul className="ml-3 list-disc">{c.titles.map((t: any) => <li key={t.title}>{t.title} <span className="text-text-muted">(T{t.tier}, {t.review_status})</span></li>)}</ul>
                        </details>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}</tbody>
          </table>
        </div>
        <dl className="mt-3 grid gap-1 text-xs md:grid-cols-2">{Object.entries(d.legend).map(([k, v]) => <div key={k}><Badge tone={TONE[k]}>{k}</Badge> <span className="text-text-secondary">{v as string}</span></div>)}</dl>
      </Card>
    </div>
  );
}
