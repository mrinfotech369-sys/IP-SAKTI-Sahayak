import type { Metadata } from 'next';
import { GeistSans } from 'geist/font/sans';
import { DM_Serif_Display } from 'next/font/google';
import './globals.css';
import { Providers } from '@/lib/providers';

const dmSerif = DM_Serif_Display({ weight: '400', subsets: ['latin'], variable: '--font-dm-serif' });

export const metadata: Metadata = {
  title: 'IP-SAKTI Sahayak',
  description: 'Evidence-grounded IP and regulatory intelligence copilot for Ayurveda.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${GeistSans.variable} ${dmSerif.variable}`}>
      <body className="antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
