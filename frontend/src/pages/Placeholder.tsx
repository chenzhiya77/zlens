export default function Placeholder({ title, ticket }: { title: string; ticket: string }) {
  return (
    <div className="rounded-xl border border-dashed border-zinc-800 px-8 py-16 text-center">
      <p className="text-sm text-zinc-400">「{title}」视图尚未交付</p>
      <p className="mt-2 text-xs text-zinc-600">
        由实施票 {ticket} 交付 — 见 docs/plans/tickets/
      </p>
    </div>
  );
}
