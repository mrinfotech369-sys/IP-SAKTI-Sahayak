'use client';

import {
  BookOpenCheck, FileSearch, FlaskConical, GitBranch, Landmark, Leaf, ScrollText, UserCheck,
} from 'lucide-react';
import Link from 'next/link';
import { useEffect, useState } from 'react';
import { LinkButton } from '@/components/ui';
import { useApp } from '@/lib/providers';

const CAPABILITIES = [
  { icon: Leaf, title: 'Innovation Intelligence', text: 'Guided profiler turns a formulation into structured, normalised technical features.' },
  { icon: FileSearch, title: 'Patent & Prior Art', text: 'Feature-to-document matrix with patent-family grouping. Overlap, never verdicts.' },
  { icon: FlaskConical, title: 'Scientific Evidence', text: 'Study cards that keep ingredient evidence separate from finished-formulation evidence.' },
  { icon: BookOpenCheck, title: 'Traditional Knowledge Context', text: 'Public and authorised TK context with explicit access limits. No TKDL scraping.' },
  { icon: Landmark, title: 'Regulatory Navigation', text: 'Provisional pathways for India, USA and Australia with a side-by-side passport.' },
  { icon: ScrollText, title: 'Citation Verification', text: 'Every claim is checked against its cited passage: supported, partial, unsupported, conflicting.' },
  { icon: GitBranch, title: 'Evidence Graph', text: 'Interactive graph where every edge carries provenance back to a source passage.' },
  { icon: UserCheck, title: 'Human Escalation', text: 'One-click review packets for IP, regulatory and domain experts, with a full audit trail.' },
];

export default function Landing() {
  const { t, lang, setLang, user } = useApp();
  const [jur, setJur] = useState('');
  useEffect(() => { try { setJur(localStorage.getItem('ipsakti.jur') || ''); } catch {} }, []);
  return (
    <div className="min-h-screen">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-6 py-5">
        <div className="flex items-center gap-2">
          <div className="grid h-8 w-8 place-items-center rounded bg-deep-green font-serif text-gold">स</div>
          <span className="font-semibold tracking-wide">{t.appTitle}</span>
        </div>
        <nav className="flex items-center gap-3 text-sm">
          <div className="flex rounded border border-surface-border text-xs" role="group" aria-label="Language">
            {(['en', 'hi'] as const).map((l) => (
              <button key={l} onClick={() => setLang(l)} aria-pressed={lang === l} className={`px-2 py-1 ${lang === l ? 'bg-deep-green text-white' : ''}`}>
                {l === 'en' ? 'English' : 'हिन्दी'}
              </button>
            ))}
          </div>
          {user ? <LinkButton href="/app">Open app</LinkButton> : <Link href="/login" className="font-medium hover:underline">{t.signIn}</Link>}
        </nav>
      </header>

      <main className="mx-auto max-w-6xl px-6">
        <section className="grid gap-10 py-14 lg:grid-cols-[1.3fr_1fr] lg:items-center">
          <div>
            <p className="mb-3 text-xs font-semibold uppercase tracking-[0.2em] text-terracotta">Evidence-Grounded IP & Regulatory Intelligence Copilot for Ayurveda</p>
            <h1 className="font-serif text-5xl leading-[1.05] md:text-6xl">{t.appTitle}</h1>
            <p className="mt-5 max-w-xl text-lg text-text-secondary">{t.tagline}</p>
            <div className="mt-6 flex flex-wrap items-center gap-3 text-xs">
              <label className="flex items-center gap-1">Language
                <select className="py-1 text-xs" value={lang} onChange={(e) => setLang(e.target.value as 'en' | 'hi')}>
                  <option value="en">English</option><option value="hi">हिन्दी</option>
                </select>
              </label>
              <label className="flex items-center gap-1">Jurisdiction
                <select className="py-1 text-xs" value={jur} onChange={(e) => { setJur(e.target.value); try { localStorage.setItem('ipsakti.jur', e.target.value); } catch {} }}>
                  <option value="">Auto-detect / ask me</option><option value="IN">India</option><option value="US">USA</option><option value="AU">Australia</option>
                </select>
              </label>
            </div>
            <div className="mt-4 grid gap-3 sm:grid-cols-3">
              {[
                [user ? '/app/innovations/new' : '/register?next=/app/innovations/new', t.startAnalysis, 'Profile a formulation → classification, pathway, IP, evidence'],
                [user ? `/app/assistant${jur ? `?jur=${jur}` : ''}` : '/login?demo=1&next=/app/assistant', lang === 'hi' ? 'आईपी / नियामक प्रश्न पूछें' : 'Ask an IP / Regulatory Question', 'Cited, verified answers — or a clear abstention'],
                [user ? '/app/coverage' : '/login?demo=1&next=/app/coverage', lang === 'hi' ? 'स्रोत देखें' : 'Explore Sources', 'What is actually ingested, per jurisdiction'],
              ].map(([href, label, sub], i) => (
                <Link key={href} href={href} className={`rounded-lg border p-4 transition ${i === 0 ? 'border-deep-green bg-deep-green text-white hover:bg-green' : 'border-surface-border bg-surface-elevated hover:border-green/50'}`}>
                  <div className="font-semibold">{label}</div>
                  <div className={`mt-1 text-xs ${i === 0 ? 'text-white/70' : 'text-text-secondary'}`}>{sub}</div>
                </Link>
              ))}
            </div>
            <div className="mt-3"><LinkButton href={user ? '/app' : '/login?demo=1'} variant="secondary">{t.exploreDemo}</LinkButton></div>
            <p className="mt-6 max-w-xl border-l-2 border-gold pl-3 text-xs text-text-secondary">{t.boundary}</p>
          </div>
          <div className="rounded-xl border border-surface-border bg-deep-green p-8 text-white">
            <ol className="space-y-4">
              {t.principle.map((p, i) => (
                <li key={p} className="flex items-baseline gap-4">
                  <span className="font-mono text-sm text-gold">0{i + 1}</span>
                  <span className="font-serif text-3xl">{p}</span>
                </li>
              ))}
            </ol>
            <p className="mt-6 text-xs text-white/70">
              Query → intent & jurisdiction → terminology expansion → hybrid retrieval (pgvector + full-text) → rerank → generate → extract claims → bind &
              verify citations → detect conflicts & staleness → abstain when evidence is insufficient.
            </p>
          </div>
        </section>

        <section className="border-t border-surface-border py-12">
          <h2 className="mb-6 font-serif text-2xl">What it does</h2>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {CAPABILITIES.map(({ icon: Icon, title, text }) => (
              <div key={title} className="rounded-lg border border-surface-border bg-surface-elevated p-4">
                <Icon className="h-5 w-5 text-terracotta" aria-hidden />
                <h3 className="mt-3 text-sm font-semibold">{title}</h3>
                <p className="mt-1 text-xs text-text-secondary">{text}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="grid gap-6 border-t border-surface-border py-12 md:grid-cols-3">
          {[
            ['Jurisdictions kept separate', 'India (AYUSH, CDSCO, FSSAI, IP India, NBA), USA (FDA) and Australia (TGA) are never mixed silently.'],
            ['Safe abstention', 'When evidence is missing, conflicting or out of scope, it says so — with what was searched and what is missing.'],
            ['Honest data labels', 'Seeded statute summaries, fictional demo patents and unverified uploads are always labelled as such.'],
          ].map(([h, p]) => (
            <div key={h}>
              <h3 className="font-semibold">{h}</h3>
              <p className="mt-1 text-sm text-text-secondary">{p}</p>
            </div>
          ))}
        </section>
      </main>
      <footer className="border-t border-surface-border py-6 text-center text-xs text-text-muted">
        IP-SAKTI Sahayak · decision support, not legal, regulatory or medical advice · does not create attorney-client privilege
      </footer>
    </div>
  );
}
