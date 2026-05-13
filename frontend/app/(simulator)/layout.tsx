/**
 * Layout for the (simulator) route group.
 *
 * The simulator is a full-width interactive surface, distinct from the
 * /results docs route. This layout intentionally has no chrome — the
 * page itself provides the top bar and panel structure.
 */

export default function SimulatorLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
