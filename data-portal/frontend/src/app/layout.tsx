import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "U-Chrom Data Portal",
  description: "Analysis-ready chromatin 3D structure datasets",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-gray-50 text-gray-900">
        <header className="border-b bg-white">
          <div className="mx-auto max-w-6xl px-4 py-4 flex items-center justify-between">
            <a href="/" className="text-lg font-semibold">U-Chrom Data Portal</a>
            <a
              href="https://github.com/Nanguage/U-Chrom"
              className="text-sm text-gray-500 hover:text-gray-900"
            >
              GitHub
            </a>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-4 py-8">{children}</main>
      </body>
    </html>
  );
}
