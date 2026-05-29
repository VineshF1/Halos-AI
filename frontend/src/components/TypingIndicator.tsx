export default function TypingIndicator() {
  return (
    <div className="flex items-center gap-1.5 px-1 py-3">
      <span className="inline-block h-2 w-2 rounded-full bg-f1-muted animate-pulse-dot [animation-delay:0s]" />
      <span className="inline-block h-2 w-2 rounded-full bg-f1-muted animate-pulse-dot [animation-delay:0.16s]" />
      <span className="inline-block h-2 w-2 rounded-full bg-f1-muted animate-pulse-dot [animation-delay:0.32s]" />
    </div>
  );
}
