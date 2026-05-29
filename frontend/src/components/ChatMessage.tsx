import type { Message } from "../types";
import { cn } from "@/lib/utils";

interface Props {
  message: Message;
}

export default function ChatMessage({ message }: Props) {
  const isUser = message.role === "user";

  return (
    <div className={cn("flex", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[75%] px-4 py-2.5 leading-relaxed text-f1-text shadow-sm",
          isUser
            ? "rounded-2xl rounded-br-none bg-black border border-f1-border/40"
            : "rounded-2xl rounded-bl-none bg-black border border-f1-border/40"
        )}
      >
        <p className="whitespace-pre-wrap break-words">{message.content}</p>
      </div>
    </div>
  );
}
