import type { Metadata } from "next";
import { Toaster } from "sonner";
import { AdminShortcut } from "@/components/admin-shortcut";
import "@fontsource/geist/400.css";
import "@fontsource/geist/500.css";
import "@fontsource/geist/600.css";
import "@fontsource/tiro-devanagari-hindi/400.css";
import "./globals.css";
export const metadata: Metadata = {
  title: "Shikayat — your AI consumer advocate. It doesn't stop when customer care replies. It stops when your issue is actually resolved.",
  description: "Shikayat — your AI consumer advocate. It doesn't stop when customer care replies. It stops when your issue is actually resolved.",
};
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><AdminShortcut />{children}<Toaster richColors /></body></html>;
}
