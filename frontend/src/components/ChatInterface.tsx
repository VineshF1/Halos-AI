import { useState, useRef, useEffect, useCallback } from "react";
import type { Message } from "../types";
import { sendMessage, wakeUpBackend } from "../api";
import ChatMessage from "./ChatMessage";
import TypingIndicator from "./TypingIndicator";
import WelcomeScreen from "./WelcomeScreen";
import ChatInput from "./ChatInput";
import { FallingPattern } from "@/components/ui/falling-pattern";

let idCounter = 0;
function nextId() {
  return `msg_${++idCounter}_${Date.now()}`;
}

export default function ChatInterface() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [waking, setWaking] = useState(false);
  const [wakeOk, setWakeOk] = useState(false);
  const wakeChecked = useRef(false);

  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  useEffect(() => {
    if (wakeChecked.current) return;
    wakeChecked.current = true;
    wakeUpBackend().then(setWakeOk);
  }, []);

  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || isLoading) return;

    setError(null);
    const userMsg: Message = { role: "user", content: text, id: nextId() };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setIsLoading(true);

    try {
      const history = [...messages, userMsg];
      const data = await sendMessage(text, history);

      const assistantMsg: Message = {
        role: "assistant",
        content: data.reply,
        id: nextId(),
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Something went wrong.";
      setError(msg);
      const errorMsg: Message = {
        role: "assistant",
        content: msg.includes("Database unavailable")
          ? `⚠️ ${msg}`
          : `Sorry, I encountered an error: ${msg}`,
        id: nextId(),
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setIsLoading(false);
    }
  }, [input, isLoading, messages]);

  function handleNewChat() {
    setMessages([]);
    setError(null);
  }

  async function handleWake() {
    setWaking(true);
    const ok = await wakeUpBackend();
    if (ok) setWakeOk(true);
    setWaking(false);
  }

  const hasMessages = messages.length > 0;

  return (
    <div className="relative flex h-screen bg-f1-black">
      <FallingPattern
        className="absolute inset-0 [mask-image:radial-gradient(ellipse_at_center,transparent,var(--background))]"
        color="#ffffff"
        backgroundColor="#000000c5"
        duration={200}
      />
      <div className="relative z-10 flex flex-1 flex-col min-w-0">
        {/* Header */}
        <header className="flex items-center justify-between shrink-0 px-4 h-14 border-b border-f1-border">
          {/* F1 logo placeholder */}
          <img src="logo.png" alt="F1 Logo" className="h-7 w-auto" />
          <div className="flex items-center gap-2">
            {/* Wake backend */}
            <button
              onClick={handleWake}
              disabled={waking}
              className={`relative flex h-9 w-9 items-center justify-center rounded-full transition-colors disabled:opacity-50 ${
                wakeOk
                  ? "text-green-400 hover:bg-green-400/10"
                  : "text-red-400 hover:bg-red-400/10"
              }`}
              title={waking ? "Waking backend..." : wakeOk ? "Backend online" : "Wake backend (click to start)"}
            >
              {waking ? (
                <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 0 1 8-8V0C5.373 0 0 5.373 0 12h4Z" />
                </svg>
              ) : (
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-5 h-5">
                  <path d="M12 2.25a.75.75 0 0 1 .75.75v2.25a.75.75 0 0 1-1.5 0V3a.75.75 0 0 1 .75-.75ZM7.5 12a4.5 4.5 0 1 1 9 0 4.5 4.5 0 0 1-9 0ZM18.894 6.166a.75.75 0 0 0-1.06-1.06l-1.591 1.59a.75.75 0 1 0 1.06 1.061l1.591-1.59ZM21.75 12a.75.75 0 0 1-.75.75h-2.25a.75.75 0 0 1 0-1.5H21a.75.75 0 0 1 .75.75ZM17.834 18.894a.75.75 0 0 0 1.06-1.06l-1.59-1.591a.75.75 0 1 0-1.061 1.06l1.59 1.591ZM12 18a.75.75 0 0 1 .75.75V21a.75.75 0 0 1-1.5 0v-2.25A.75.75 0 0 1 12 18ZM7.758 17.303a.75.75 0 0 0-1.061-1.06l-1.591 1.59a.75.75 0 0 0 1.06 1.061l1.591-1.59ZM6.75 12a.75.75 0 0 1-.75.75H3.75a.75.75 0 0 1 0-1.5H6a.75.75 0 0 1 .75.75ZM6.172 7.757a.75.75 0 0 0 1.061-1.06L5.643 5.106a.75.75 0 1 0-1.06 1.06l1.59 1.591Z" />
                </svg>
              )}
              {/* Glow ring */}
              {!wakeOk && !waking && (
                <span className="absolute inset-0 rounded-full animate-ping bg-red-400/20" />
              )}
            </button>
            {/* New Chat */}
            <button
              onClick={handleNewChat}
              className="flex h-9 w-9 items-center justify-center rounded-full text-f1-muted hover:bg-f1-surface hover:text-f1-text transition-colors"
              title="New Chat"
            >
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-5 h-5">
                <path fillRule="evenodd" d="M4.755 10.059a7.5 7.5 0 0 1 12.548-3.364l1.903 1.903h-3.183a.75.75 0 1 0 0 1.5h4.992a.75.75 0 0 0 .75-.75V4.356a.75.75 0 0 0-1.5 0v3.18l-1.9-1.9A9 9 0 0 0 3.306 9.67a.75.75 0 1 0 1.45.388Zm15.408 3.352a.75.75 0 0 0-.919.53 7.5 7.5 0 0 1-12.548 3.364l-1.902-1.903h3.183a.75.75 0 0 0 0-1.5H2.984a.75.75 0 0 0-.75.75v4.992a.75.75 0 0 0 1.5 0v-3.18l1.9 1.9a9 9 0 0 0 15.059-4.035.75.75 0 0 0-.53-.918Z" clipRule="evenodd" />
              </svg>
            </button>
          </div>
        </header>

        {/* Chat area */}
        {hasMessages ? (
          <div className="flex-1 overflow-y-auto px-4 py-6 sm:px-6">
            <div className="mx-auto max-w-3xl flex flex-col gap-5">
              {messages.map((msg) => (
                <ChatMessage key={msg.id} message={msg} />
              ))}
              {isLoading && <TypingIndicator />}
              {error && !isLoading && (
                <p className="text-center text-xs text-f1-red/70">
                  Connection issue. Check your backend.
                </p>
              )}
              <div ref={bottomRef} />
            </div>
          </div>
        ) : (
          <WelcomeScreen />
        )}

        {/* Floating input */}
        <div className={hasMessages ? "sticky bottom-0 bg-gradient-to-t from-f1-black via-f1-black/95 to-transparent pt-6 pb-3" : "pb-3"}>
          <ChatInput
            value={input}
            onChange={setInput}
            onSend={handleSend}
            disabled={isLoading}
          />
        </div>
      </div>
    </div>
  );
}
