'use client';

import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  BarChart3, Grid3x3, Lock, MessageSquareWarning, BookOpen, Bot, ClipboardList, Database, FileStack, FileText, FlaskConical, GitBranch,
  Landmark, Layers, LayoutDashboard, Leaf, LogOut, Map, Menu, PlusCircle, ScrollText, Settings, ShieldAlert, ShieldCheck,
} from 'lucide-react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { BackButton } from '@/components/back';
import { Spinner, cx } from '@/components/ui';
import { get, post, setWorkspaceId } from '@/lib/api';
import { useApp } from '@/lib/providers';

type Item = { href: string; label: string; icon: any };

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { t, lang, setLang, user, userLoading, workspaceId, switchWorkspace } = useApp();
  const router = useRouter();
  const path = usePathname();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const health = useQuery({ queryKey: ['health'], queryFn: () => get('/health'), refetchInterval: 60_000, enabled: !!user });

  useEffect(() => {
    if (!userLoading && user === null) router.replace(`/login?next=${encodeURIComponent(path)}`);
  }, [user, userLoading, router, path]);
  useEffect(() => {
    setOpen(false);
  }, [path]);

  if (userLoading || !user) {
    return <div className="grid min-h-screen place-items-center"><Spinner label="Checking your session…" /></div>;
  }

  const groups: { title?: string; items: Item[] }[] = [
    { items: [{ href: '/app', label: t.nav.dashboard, icon: LayoutDashboard }] },
    { title: t.nav.myInnovations, items: [
      { href: '/app/innovations', label: t.nav.allInnovations, icon: Leaf },
      { href: '/app/innovations/new', label: t.nav.createInnovation, icon: PlusCircle },
    ] },
    { title: t.nav.research, items: [
      { href: '/app/assistant', label: t.nav.assistant, icon: Bot },
      { href: '/app/research/scientific', label: t.nav.scientific, icon: FlaskConical },
      { href: '/app/research/patents', label: t.nav.patents, icon: FileStack },
      { href: '/app/research/tk', label: t.nav.tk, icon: BookOpen },
      { href: '/app/research/regulatory', label: t.nav.regulatory, icon: Landmark },
    ] },
    { title: t.nav.analysis, items: [
      { href: '/app/analysis/evidence', label: t.nav.evidenceMap, icon: Map },
      { href: '/app/analysis/graph', label: t.nav.graph, icon: GitBranch },
      { href: '/app/analysis/gaps', label: t.nav.gaps, icon: ShieldAlert },
      { href: '/app/analysis/risk', label: t.nav.risk, icon: BarChart3 },
    ] },
    { title: t.nav.reports, items: [
      { href: '/app/reports', label: t.nav.evidenceReports, icon: FileText },
      { href: '/app/escalations', label: t.nav.escalations, icon: ClipboardList },
      { href: '/app/feedback', label: t.nav.feedback, icon: MessageSquareWarning },
    ] },
    { title: t.nav.workspace, items: [
      { href: '/app/coverage', label: t.nav.coverage, icon: Grid3x3 },
      { href: '/app/sources', label: t.nav.sources, icon: Database },
      { href: '/app/documents', label: t.nav.documents, icon: Layers },
      { href: '/app/audit', label: t.nav.audit, icon: ScrollText },
      { href: '/app/privacy', label: t.nav.privacy, icon: Lock },
      { href: '/app/settings', label: t.nav.settings, icon: Settings },
    ] },
  ];
  // Intentionally no "Admin" nav group here: the admin console (/admin/*) is a fully separate
  // area with its own login, session and layout — see app/admin/layout.tsx. Mixing it into this
  // sidebar would defeat that separation. ADMIN-role users get a single discovery link below,
  // in the footer, which sends them to the admin console's own sign-in (an app session here is
  // never sufficient by itself).

  const isActive = (href: string) => (href === '/app' ? path === '/app' : path === href || (path.startsWith(href + '/') && href !== '/app/innovations') || (href === '/app/innovations' && path.startsWith('/app/innovations/') && !path.startsWith('/app/innovations/new')));
  const status = health.data?.status;

  async function signOut() {
    try {
      await post('/auth/logout');
    } finally {
      setWorkspaceId(null);
      qc.clear();
      window.location.href = '/login';
    }
  }

  const nav = (
    <nav className="flex h-full flex-col" aria-label="Main">
      <Link href="/app" className="flex items-center gap-2 px-4 py-4">
        <div className="grid h-8 w-8 place-items-center rounded bg-gold font-serif text-deep-green">स</div>
        <div className="leading-tight">
          <div className="text-sm font-semibold text-white">{t.appTitle}</div>
          <div className="text-[10px] uppercase tracking-wider text-white/50">Evidence copilot</div>
        </div>
      </Link>
      <div className="flex-1 overflow-y-auto px-2 pb-4">
        {groups.map((g, i) => (
          <div key={i} className="mt-3">
            {g.title && <div className="px-2 pb-1 text-[10px] font-semibold uppercase tracking-widest text-white/40">{g.title}</div>}
            {g.items.map(({ href, label, icon: Icon }) => (
              <Link key={href} href={href} aria-current={isActive(href) ? 'page' : undefined}
                className={cx('flex items-center gap-2 rounded px-2 py-1.5 text-[13px]', isActive(href) ? 'bg-white/10 font-medium text-white' : 'text-white/70 hover:bg-white/5 hover:text-white')}>
                <Icon className="h-4 w-4 shrink-0" aria-hidden />
                {label}
              </Link>
            ))}
          </div>
        ))}
      </div>
      <div className="border-t border-white/10 p-3 text-[11px] text-white/60">
        <Link href="/app/settings" className="flex items-center gap-1.5">
          <span className={cx('h-2 w-2 rounded-full', status === 'ok' ? 'bg-emerald-400' : status ? 'bg-amber-400' : 'bg-white/30')} />
          System {status || 'checking'} · LLM {health.data?.llm_provider || '…'}
        </Link>
        {user.role === 'ADMIN' && (
          <Link href="/admin/login" className="mt-2 flex items-center gap-1.5 rounded border border-white/10 px-2 py-1 text-white/80 hover:border-white/30 hover:text-white">
            <ShieldCheck className="h-3.5 w-3.5" aria-hidden />
            {lang === 'hi' ? 'व्यवस्थापक कंसोल (अलग साइन-इन) →' : 'Admin console (separate sign-in) →'}
          </Link>
        )}
      </div>
    </nav>
  );

  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 bg-deep-green lg:block">{nav}</aside>
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <button className="absolute inset-0 bg-black/40" aria-label="Close menu" onClick={() => setOpen(false)} />
          <aside className="relative h-full w-64 bg-deep-green">{nav}</aside>
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="no-print sticky top-0 z-30 flex items-center gap-2 sm:gap-3 border-b border-surface-border bg-darkbg/95 px-4 py-2 backdrop-blur">
          <button className="lg:hidden" onClick={() => setOpen(true)} aria-label="Open menu"><Menu className="h-5 w-5" /></button>
          {path !== '/app' && <BackButton label={lang === 'hi' ? 'वापस' : 'Back'} />}
          <label className="flex items-center gap-2 text-xs">
            <span className="hidden text-text-muted sm:inline">Workspace</span>
            <select className="max-w-[40vw] py-1 text-xs sm:max-w-none" value={workspaceId || ''} onChange={(e) => switchWorkspace(e.target.value)} aria-label="Workspace">
              {user.workspaces.map((w) => (
                <option key={w.id} value={w.id}>{w.name} ({w.role.toLowerCase()}){w.confidential_mode ? ' · confidential' : ''}</option>
              ))}
            </select>
          </label>
          <div className="ml-auto flex shrink-0 items-center gap-2 sm:gap-3">
            <div className="flex rounded border border-surface-border text-xs" role="group" aria-label="Language">
              {(['en', 'hi'] as const).map((l) => (
                <button key={l} onClick={() => setLang(l)} aria-pressed={lang === l} className={cx('px-2 py-1', lang === l && 'bg-deep-green text-white')}>
                  {l === 'en' ? 'English' : 'हिन्दी'}
                </button>
              ))}
            </div>
            <span className="hidden text-xs text-text-secondary md:inline">{user.name}{user.role === 'ADMIN' ? ' · admin' : ''}</span>
            <button onClick={signOut} className="flex items-center gap-1 text-xs text-text-secondary hover:text-text-main" aria-label={t.signOut}>
              <LogOut className="h-4 w-4" /> <span className="hidden sm:inline">{t.signOut}</span>
            </button>
          </div>
        </header>
        <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 md:px-8">{children}</main>
      </div>
    </div>
  );
}

