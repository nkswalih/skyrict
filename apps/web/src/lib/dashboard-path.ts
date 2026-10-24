/**
 * Convert the browser's pathname to the internal `/dashboard/*` form. The
 * workspace surface serves the dashboard at the tenant root, so the public URL
 * strips the prefix (`/roles`, `/members`) and middleware rewrites it back to
 * `/dashboard/roles` etc. `usePathname()` reports the public path, so
 * normalize before matching.
 * Updated to properly handle /demo/erp routes for accurate sub-nav highlighting.
 */
export function normalizeDashboardPath(pathname: string): string {
  if (pathname === "/") return "/dashboard";
  if (pathname === "/demo/erp") return "/dashboard/erp";
  if (pathname.startsWith("/demo/erp/")) {
    return `/dashboard${pathname.slice("/demo".length)}`;
  }
  return pathname.startsWith("/dashboard")
    ? pathname
    : `/dashboard${pathname}`;
}