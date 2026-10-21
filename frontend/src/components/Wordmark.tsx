/** CampusSignal wordmark: the accent "signal" dot is its only use of colour (Design.md §2). */
export function Wordmark() {
  return (
    <span className="inline-flex items-baseline gap-1 font-heading text-xl font-semibold tracking-tight text-fg">
      CampusSignal
      <span aria-hidden="true" className="inline-block size-2 rounded-full bg-accent" />
    </span>
  );
}
