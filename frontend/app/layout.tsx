import type { Metadata } from "next";
import { Toaster } from "sonner";
import "@fontsource/geist/400.css";
import "@fontsource/geist/500.css";
import "@fontsource/geist/600.css";
import "./globals.css";
export const metadata: Metadata = {
  title: "Shikayat: AI that fights customer care for you",
  description: "Your complaint. A clear path forward.",
};
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}<Toaster richColors /></body></html>;
}
