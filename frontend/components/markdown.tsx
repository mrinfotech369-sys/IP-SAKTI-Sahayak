'use client';

import { Fragment, ReactNode } from 'react';

/** Minimal, safe Markdown renderer (no raw HTML) for generated reports. */
function inline(text: string): ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*|_[^_]+_|`[^`]+`)/g);
  return parts.map((p, i) => {
    if (p.startsWith('**') && p.endsWith('**')) return <strong key={i}>{p.slice(2, -2)}</strong>;
    if (p.startsWith('_') && p.endsWith('_') && p.length > 2) return <em key={i}>{p.slice(1, -1)}</em>;
    if (p.startsWith('`') && p.endsWith('`')) return <code key={i}>{p.slice(1, -1)}</code>;
    return <Fragment key={i}>{p.replace(/ {2}$/, '')}</Fragment>;
  });
}

export function Markdown({ source }: { source: string }) {
  const lines = source.split('\n');
  const out: ReactNode[] = [];
  let i = 0;
  while (i < lines.length) {
    const l = lines[i];
    if (l.startsWith('|')) {
      const rows: string[][] = [];
      while (i < lines.length && lines[i].startsWith('|')) {
        if (!/^\|[-| ]+\|$/.test(lines[i])) rows.push(lines[i].slice(1, -1).split('|').map((c) => c.trim()));
        i++;
      }
      out.push(
        <table key={i}><thead><tr>{rows[0].map((c, j) => <th key={j}>{inline(c)}</th>)}</tr></thead>
          <tbody>{rows.slice(1).map((r, k) => <tr key={k}>{r.map((c, j) => <td key={j}>{inline(c)}</td>)}</tr>)}</tbody></table>
      );
      continue;
    }
    if (l.startsWith('- ')) {
      const items: string[] = [];
      while (i < lines.length && (lines[i].startsWith('- ') || lines[i].startsWith('  '))) {
        if (lines[i].startsWith('- ')) items.push(lines[i].slice(2));
        else items[items.length - 1] += ' ' + lines[i].trim();
        i++;
      }
      out.push(<ul key={i}>{items.map((it, j) => <li key={j}>{inline(it)}</li>)}</ul>);
      continue;
    }
    if (l.startsWith('### ')) out.push(<h3 key={i}>{inline(l.slice(4))}</h3>);
    else if (l.startsWith('## ')) out.push(<h2 key={i}>{inline(l.slice(3))}</h2>);
    else if (l.startsWith('# ')) out.push(<h1 key={i}>{inline(l.slice(2))}</h1>);
    else if (l.startsWith('> ')) out.push(<blockquote key={i}>{inline(l.slice(2))}</blockquote>);
    else if (l.trim()) out.push(<p key={i}>{inline(l)}</p>);
    i++;
  }
  return <div className="prose-report">{out}</div>;
}
