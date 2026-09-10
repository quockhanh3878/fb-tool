import type { Metadata } from "next";
import { Plus_Jakarta_Sans } from "next/font/google";

import { ToastProvider } from "@/components/ui";
import { AuthProvider } from "@/lib/auth";
import "./globals.css";

const sans = Plus_Jakarta_Sans({
  subsets: ["latin", "vietnamese"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
  variable: "--font-sans",
});

export const metadata: Metadata = {
  title: "CommHunter AI — Nền tảng Săn Lead & Tương tác Facebook Tự động",
  description: "Giải pháp SaaS săn khách tiềm năng trong group Facebook, lọc AI thông minh và tương tác tự động an toàn.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="vi" suppressHydrationWarning className={sans.variable}>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `
              try {
                const theme = localStorage.getItem('commhunter_theme') || 
                  (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
                if (theme === 'dark') document.documentElement.classList.add('dark');
                else document.documentElement.classList.remove('dark');
              } catch (e) {}
            `,
          }}
        />
      </head>
      <body className="font-sans antialiased min-h-screen bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-slate-100">
        <AuthProvider>
          <ToastProvider>{children}</ToastProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
