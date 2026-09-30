'use client';

import { useParams } from 'next/navigation';
import { RegulatoryCard } from '@/components/evidence';
import { Card, ErrorState, FreshnessBadge, Notice, Spinner } from '@/components/ui';
import { useInnovationData } from '@/lib/hooks';

const NAMES: Record<string, string> = { IN: 'India', US: 'USA', AU: 'Australia' };

function Cell({ v }: { v: any }) {
  if (v == null) return <span className="text-text-muted">— not a target market</span>;
  if (Array.isArray(v)) return <ul className="ml-4 list-disc">{v.map((x) => <li key={x}>{x}</li>)}</ul>;
  if (['Current', 'Recently checked', 'Potentially stale', 'Superseded', 'Unknown'].includes(v)) return <FreshnessBadge status={v} />;
  return <>{v}</>;
}

export default function RegulatoryTab() {
  const { id } = useParams<{ id: string }>();
  const q = useInnovationData(id, 'regulatory');
  if (q.isLoading) return <Spinner label="Comparing jurisdictions…" />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const { passport, comparison } = q.data;
  const js = ['IN', 'US', 'AU'].filter((j) => passport[j]);
  return (
    <div className="space-y-5">
      <div className="flex items-baseline justify-between">
        <h2 className="font-serif text-2xl tracking-wide">REGULATORY PASSPORT</h2>
        <span className="text-xs text-text-muted">Jurisdictions are evaluated separately and never mixed.</span>
      </div>
      {js.length === 0 && <Notice tone="info">Which market are you evaluating? Select target markets in the Classification tab.</Notice>}
      <div className="grid gap-4 lg:grid-cols-3">
        {js.map((j) => <RegulatoryCard key={j} entry={passport[j]} />)}
      </div>
      <Card title="Jurisdiction comparison" subtitle="India · USA · Australia">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-surface-muted text-text-secondary">
              <tr><th className="w-40 px-2 py-2">Dimension</th>{['IN', 'US', 'AU'].map((j) => <th key={j} className="px-2">{NAMES[j]}</th>)}</tr>
            </thead>
            <tbody>
              {comparison.map((row: any) => (
                <tr key={row.dimension} className="border-t border-surface-border align-top">
                  <th scope="row" className="px-2 py-2 font-semibold">{row.dimension}</th>
                  {['IN', 'US', 'AU'].map((j) => <td key={j} className="px-2 py-2"><Cell v={row[j]} /></td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
