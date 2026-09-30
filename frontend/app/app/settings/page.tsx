'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { FormEvent, useEffect, useState } from 'react';
import { Badge, Button, Card, ErrorState, Field, Notice, PageHeader, Spinner } from '@/components/ui';
import { get, patch, post } from '@/lib/api';
import { useApp } from '@/lib/providers';

export default function Settings() {
  const { workspaceId, lang, setLang, switchWorkspace } = useApp();
  const qc = useQueryClient();
  const ws = useQuery({ queryKey: ['workspace', workspaceId], queryFn: () => get(`/workspaces/${workspaceId}`), enabled: !!workspaceId });
  const [form, setForm] = useState<any>({});
  const [invite, setInvite] = useState({ email: '', role: 'RESEARCHER' });
  const [newWs, setNewWs] = useState('');
  useEffect(() => { if (ws.data) setForm(ws.data); }, [ws.data]);
  const save = useMutation({
    mutationFn: () => patch(`/workspaces/${workspaceId}`, { name: form.name, confidential_mode: form.confidential_mode, retention_policy: form.retention_policy, external_retrieval_allowed: form.external_retrieval_allowed }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['workspace'] }); qc.invalidateQueries({ queryKey: ['me'] }); },
  });
  const add = useMutation({ mutationFn: () => post(`/workspaces/${workspaceId}/members`, invite), onSuccess: () => qc.invalidateQueries({ queryKey: ['workspace'] }) });
  const create = useMutation({ mutationFn: () => post<any>('/workspaces', { name: newWs }), onSuccess: async (w) => { await qc.invalidateQueries({ queryKey: ['me'] }); switchWorkspace(w.id); setNewWs(''); } });
  if (ws.isLoading) return <Spinner />;
  if (ws.isError) return <ErrorState error={ws.error} onRetry={() => ws.refetch()} />;
  const canAdmin = ['OWNER', 'ADMIN'].includes(ws.data?.role);
  return (
    <div className="space-y-5">
      <PageHeader title="Settings" subtitle={`Workspace “${ws.data?.name}” · your role: ${ws.data?.role}`} />
      <div className="grid gap-5 lg:grid-cols-2">
        <Card title="Confidential workspace controls">
          <form onSubmit={(e: FormEvent) => { e.preventDefault(); save.mutate(); }} className="space-y-3">
            <Field label="Workspace name"><input className="w-full" value={form.name || ''} onChange={(e) => setForm({ ...form, name: e.target.value })} disabled={!canAdmin} /></Field>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={!!form.confidential_mode} onChange={(e) => setForm({ ...form, confidential_mode: e.target.checked })} disabled={!canAdmin} /> Confidential mode (isolation, audit, disclosure warnings)</label>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={!!form.external_retrieval_allowed} onChange={(e) => setForm({ ...form, external_retrieval_allowed: e.target.checked })} disabled={!canAdmin} /> Allow external retrieval (warn before sending innovation details outside)</label>
            <Field label="Retention policy">
              <select className="w-full" value={form.retention_policy || ''} onChange={(e) => setForm({ ...form, retention_policy: e.target.value })} disabled={!canAdmin}>
                {['RETAIN_90_DAYS', 'RETAIN_365_DAYS', 'RETAIN_INDEFINITELY'].map((r) => <option key={r}>{r}</option>)}
              </select>
            </Field>
            {canAdmin ? <Button type="submit" loading={save.isPending}>Save</Button> : <Notice tone="info">Only workspace owners/admins can change these settings.</Notice>}
            {save.isError && <ErrorState error={save.error} />}
            {save.isSuccess && <Notice tone="ok">Saved and recorded in the audit trail.</Notice>}
          </form>
        </Card>
        <Card title="Members">
          <ul className="mb-4 divide-y divide-surface-border text-sm">
            {ws.data?.members?.map((m: any) => <li key={m.user_id} className="flex justify-between py-1.5"><span>{m.name} <span className="text-xs text-text-muted">{m.email}</span></span><Badge>{m.role}</Badge></li>)}
          </ul>
          {canAdmin && (
            <form onSubmit={(e: FormEvent) => { e.preventDefault(); add.mutate(); }} className="flex flex-wrap gap-2">
              <input className="flex-1" type="email" placeholder="colleague@example.org" value={invite.email} onChange={(e) => setInvite({ ...invite, email: e.target.value })} aria-label="Member email" />
              <select value={invite.role} onChange={(e) => setInvite({ ...invite, role: e.target.value })} aria-label="Role">{['ADMIN', 'RESEARCHER', 'REVIEWER', 'VIEWER'].map((r) => <option key={r}>{r}</option>)}</select>
              <Button type="submit" variant="secondary" loading={add.isPending}>Add</Button>
            </form>
          )}
          {add.isError && <div className="mt-2"><ErrorState error={add.error} /></div>}
        </Card>
        <Card title="Preferences">
          <Field label="Language">
            <select value={lang} onChange={(e) => setLang(e.target.value as any)}><option value="en">English</option><option value="hi">हिन्दी</option></select>
          </Field>
        </Card>
        <Card title="Create another workspace">
          <form onSubmit={(e: FormEvent) => { e.preventDefault(); if (newWs.length >= 2) create.mutate(); }} className="flex gap-2">
            <input className="flex-1" value={newWs} onChange={(e) => setNewWs(e.target.value)} placeholder="Workspace name" aria-label="New workspace name" />
            <Button type="submit" variant="secondary" loading={create.isPending}>Create</Button>
          </form>
          {create.isError && <div className="mt-2"><ErrorState error={create.error} /></div>}
        </Card>
      </div>
    </div>
  );
}
