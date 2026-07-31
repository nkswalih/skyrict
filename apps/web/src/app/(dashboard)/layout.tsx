export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div>
      <nav>
        <span>Skyrict Dashboard</span>
      </nav>
      <main>{children}</main>
    </div>
  );
}
