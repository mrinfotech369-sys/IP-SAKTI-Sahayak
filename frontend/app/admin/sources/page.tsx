'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { FormEvent, useState } from 'react';
import { Badge, Button, Card, ErrorState, Field, FreshnessBadge, PageHeader, Spinner, TierBadge, fmtDate } from '@/components/ui';
import { get, patch, post } from '@/lib/api';

const EMPTY = { name: '', authority: '', authority_tier: 1, jurisdiction: 'IN', source_type: 'REGULATION', base_url: '', access_level: 'PUBLIC', description: '', update_frequency_days: 90, curator: '' };

export default function AdminSources() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['admin-sources'], queryFn: () => get<any[]>('/admin/sources') });
  const [form, setForm] = useState<any>(EMPTY);
  const create = useMutation({
    mutationFn: () => post('/admin/sources', { ...form, authority_tier: Number(form.authority_tier), base_url: form.base_url || null }),
    onSuccess: () => { setForm(EMPTY); qc.invalidateQueries({ queryKey: ['admin-sources'] }); },
  });
  const upd = useMutation({ mutationFn: ({ id, body }: any) => patch(`/admin/sources/${id}`, body), onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-sources'] }) });
  const set = (k: string) => (e: any) => setForm({ ...form, [k]: e.target.value });

  return (
    <div className="space-y-5">
      <PageHeader eyebrow="Admin console" title="Source Registry" subtitle="Add, edit, disable sources; set authority tier, jurisdiction, URL and freshness (curator + update frequency). Changes are audited." />
      <Card title="Register a source">
        <form onSubmit={(e: FormEvent) => { e.preventDefault(); create.mutate(); }} className="grid gap-3 md:grid-cols-4">
          <Field label="Name" required><input className="w-full" value={form.name} onChange={set('name')} /></Field>
          <Field label="Authority" required><input className="w-full" value={form.authority} onChange={set('authority')} /></Field>
          <Field label="Tier"><select className="w-full" value={form.authority_tier} onChange={set('authority_tier')}>{[1, 2, 3, 4, 5].map((t) => <option key={t}>{t}</option>)}</select></Field>
          <Field label="Jurisdiction"><select className="w-full" value={form.jurisdiction} onChange={set('jurisdiction')}>{['IN', 'US', 'AU', 'INTERNATIONAL'].map((t) => <option key={t}>{t}</option>)}</select></Field>
          <Field label="Type"><input className="w-full" value={form.source_type} onChange={set('source_type')} /></Field>
          <Field label="URL"><input className="w-full" value={form.base_url} onChange={set('base_url')} /></Field>
          <Field label="Access"><select className="w-full" value={form.access_level} onChange={set('access_level')}>{['PUBLIC', 'RESTRICTED_RECORDS_PUBLIC_INFO', 'WORKSPACE', 'RESTRICTED'].map((t) => <option key={t}>{t}</option>)}</select></Field>
          <Field label="Update every (days)"><input type="number" min={1} className="w-full" value={form.update_frequency_days} onChange={set('update_frequency_days')} /></Field>
          <Field label="Curator"><input className="w-full" value={form.curator} onChange={set('curator')} placeholder="Who re-verifies this source" /></Field>
          <Field label="Description"><input className="w-full" value={form.description} onChange={set('description')} /></Field>
          <div className="md:col-span-4"><Button type="submit" loading={create.isPending} disabled={form.name.length < 2 || form.authority.length < 2}>Register source</Button></div>
        </form>
        {create.isError && <div className="mt-2"><ErrorState error={create.error} /></div>}
      </Card>
      {q.isLoading && <Spinner />}
      {q.isError && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
      {upd.isError && <ErrorState error={upd.error} />}
      <div className="overflow-x-auto rounded-lg border border-surface-border bg-surface-elevated">
        <table className="w-full text-left text-sm">
          <thead className="bg-surface-muted text-xs text-text-secondary"><tr><th className="px-3 py-2">Source</th><th>Tier</th><th>Jurisdiction</th><th>Last checked</th><th>Curator</th><th>Status</th><th>Docs</th><th>Actions</th></tr></thead>
          <tbody>{q.data?.map((s) => (
            <tr key={s.id} className="border-t border-surface-border align-top">
              <td className="px-3 py-2"><div className="font-medium">{s.name}</div><div className="text-xs text-text-muted">{s.authority}{s.base_url ? ` · ${s.base_url}` : ''}</div></td>
              <td><TierBadge tier={s.authority_tier} /></td><td>{s.jurisdiction}</td><td className="text-xs">{fmtDate(s.last_checked)}</td>
              <td className="text-xs">{s.curator}<div className="text-text-muted">every {s.update_frequency_days}d</div></td>
              <td>{s.active ? <FreshnessBadge status={s.status} /> : <Badge tone="danger">inactive</Badge>}</td><td>{s.documents}</td>
              <td className="space-x-1 whitespace-nowrap">
                <Button size="sm" variant="secondary" onClick={() => upd.mutate({ id: s.id, body: { mark_checked: true } })}>Mark checked</Button>
                <Button size="sm" variant="ghost" onClick={() => upd.mutate({ id: s.id, body: { active: !s.active } })}>{s.active ? 'Deactivate' : 'Activate'}</Button>
              </td>
            </tr>
          ))}</tbody>
        </table>
      </div>
    </div>
  );
}
