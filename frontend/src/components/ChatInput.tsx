import { type FormEvent, useRef, useEffect } from "react";

interface Props {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  disabled?: boolean;
}

export default function ChatInput({
  value,
  onChange,
  onSend,
  disabled = false,
}: Props) {
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!disabled && inputRef.current) {
      inputRef.current.focus();
    }
  }, [disabled]);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (value.trim() && !disabled) onSend();
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  }

  function autoResize() {
    const el = inputRef.current;
    if (el) {
      el.style.height = "auto";
      el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
    }
  }

  return (
    <div className="w-full max-w-3xl mx-auto px-4 pb-2">
      <form
        onSubmit={handleSubmit}
        className="flex items-center gap-2 rounded-full border border-f1-border bg-black px-4 py-2 shadow-md shadow-black/40"
      >
        <textarea
          ref={inputRef}
          value={value}
          onChange={(e) => {
            onChange(e.target.value);
            autoResize();
          }}
          onKeyDown={handleKeyDown}
          placeholder="Ask about Formula 1..."
          rows={1}
          disabled={disabled}
          className="flex-1 resize-none bg-transparent py-2 text-sm text-f1-text placeholder-f1-muted outline-none disabled:opacity-50"
        />

        <button
          type="submit"
          disabled={!value.trim() || disabled}
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-white/10 text-white/90 transition-all hover:bg-white/20 hover:text-white active:scale-95 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4">
            <path d="M3.478 2.404a.75.75 0 0 0-.926.941l2.432 7.905H13.5a.75.75 0 0 1 0 1.5H4.984l-2.432 7.905a.75.75 0 0 0 .926.94 60.519 60.519 0 0 0 18.445-8.986.75.75 0 0 0 0-1.218A60.517 60.517 0 0 0 3.478 2.404Z" />
          </svg>
        </button>
      </form>

      <p className="mt-2 text-center text-[11px] text-f1-muted/60">
        Halos AI may occasionally display inaccurate answers. Please verify.
      </p>
    </div>
  );
}
