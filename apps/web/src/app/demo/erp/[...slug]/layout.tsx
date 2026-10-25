import { notFound } from "next/navigation";

import { isDemoErpRoute } from "@/lib/demo/demo-routes";

/**
 * Server-side allowlist for the demo catch-all. Without this, every unknown
 * slug rendered the generic fallback with HTTP 200 (BUG-DEMO-006). The client
 * page still keeps a friendly fallback for in-app navigation, but a real URL
 * now returns a real 404.
 */
export default async function DemoErpSlugLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ slug: string[] }>;
}) {
  const { slug } = await params;
  if (!isDemoErpRoute(slug.join("/"))) notFound();
  return children;
}
