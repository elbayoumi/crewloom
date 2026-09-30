import './globals.css';
import type { ReactNode } from 'react';

export const metadata = { title: 'Crewloom Dashboard', description: 'Live monitoring for Crewloom roles, memory, tools, and runs.' };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
