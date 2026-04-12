import { useEffect, useRef, useState } from "react";
import FlameIcon from "./FlameIcon.jsx";
import CitationModal from "./CitationModal.jsx";

/* ─── Typing indicator ─────────────────────────────────── */

function TypingIndicator() {
  return (
    <div className="message-enter flex gap-4">
      <div className="w-8 h-8 rounded-full bg-orange-100 dark:bg-orange-900/30 flex items-center justify-center flex-shrink-0">
        <FlameIcon className="w-4 h-4 text-orange-500" />
      </div>
      <div className="flex items-center gap-1 px-4 py-4 bg-white dark:bg-gray-900 rounded-2xl border border-gray-100 dark:border-gray-800">
        <div className="w-2 h-2 bg-gray-400 rounded-full typing-dot" />
        <div className="w-2 h-2 bg-gray-400 rounded-full typing-dot" />
        <div className="w-2 h-2 bg-gray-400 rounded-full typing-dot" />
      </div>
    </div>
  );
}

/* ─── Citation pills ────────────────────────────────────── */

function Citations({ citations, onCitationClick }) {
  if (!citations?.length) return null;
  return (
    <div className="mt-2 pt-2 border-t border-gray-200 dark:border-gray-700 flex flex-wrap gap-2">
      {citations.map((c, i) => (
        <button
          key={i}
          className="citation-pill"
          onClick={() => onCitationClick(c)}
          title={c.excerpt}
        >
          {c.label}
        </button>
      ))}
    </div>
  );
}

/* ─── Stats line ────────────────────────────────────────── */

function StatsLine({ stats }) {
  if (!stats) return null;
  const parts = [
    stats.tokens_generated && `${stats.tokens_generated} tokens`,
    stats.tokens_per_second && `${stats.tokens_per_second} tok/s`,
    stats.rag_latency_ms && `RAG ${stats.rag_latency_ms}ms`,
  ].filter(Boolean);
  if (!parts.length) return null;
  return (
    <p className="text-[10px] text-gray-500 dark:text-gray-500 mt-1.5">
      {parts.join(" · ")}
    </p>
  );
}

/* ─── Individual message ────────────────────────────────── */

function Message({ msg, onCitationClick }) {
  const isUser = msg.role === "user";

  if (isUser) {
    return (
      <div className="message-enter flex gap-4 flex-row-reverse">
        <div className="w-8 h-8 rounded-full bg-gray-300 dark:bg-gray-600 flex items-center justify-center text-xs font-medium flex-shrink-0">
          Eu
        </div>
        <div className="flex-1 text-right">
          <div className="inline-block max-w-[85%] bg-gray-100 dark:bg-gray-800 text-gray-900 dark:text-gray-100 rounded-2xl px-4 py-2.5 text-sm leading-relaxed shadow-sm border border-gray-200 dark:border-gray-700">
            {msg.content}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="message-enter flex gap-4">
      <div className="w-8 h-8 rounded-full bg-orange-100 dark:bg-orange-900/30 flex items-center justify-center flex-shrink-0 mt-0.5">
        <FlameIcon className="w-4 h-4 text-orange-500" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="inline-block max-w-[85%] bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 rounded-2xl px-4 py-2.5 text-sm leading-relaxed shadow-sm border border-gray-100 dark:border-gray-800">
          {msg.error ? (
            <p className="text-red-500">{msg.error}</p>
          ) : (
            <div className="whitespace-pre-wrap">{msg.content}</div>
          )}
          {!msg.streaming && (
            <>
              <Citations
                citations={msg.citations}
                onCitationClick={onCitationClick}
              />
              <StatsLine stats={msg.stats} />
            </>
          )}
        </div>
      </div>
    </div>
  );
}

/* ─── System note ───────────────────────────────────────── */

function SystemNote({ text }) {
  return (
    <div className="flex justify-center my-4">
      <span className="text-xs text-gray-500 bg-gray-100 dark:bg-gray-800 px-3 py-1 rounded-full">
        {text}
      </span>
    </div>
  );
}

/* ─── Main ChatArea ─────────────────────────────────────── */

export default function ChatArea({ messages, isStreaming, systemNotes }) {
  const bottomRef = useRef(null);
  const [citationModal, setCitationModal] = useState(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isStreaming]);

  return (
    <>
      <div className="flex-1 overflow-y-auto scroll-smooth">
        <div className="max-w-3xl mx-auto px-4 pt-4 pb-32 space-y-6">
          {messages.map((msg) => (
            <Message
              key={msg.id}
              msg={msg}
              onCitationClick={setCitationModal}
            />
          ))}

          {systemNotes?.map((note, i) => (
            <SystemNote key={i} text={note} />
          ))}

          {isStreaming &&
            messages[messages.length - 1]?.streaming === false && (
              <TypingIndicator />
            )}

          <div ref={bottomRef} />
        </div>
      </div>

      <CitationModal
        citation={citationModal}
        onClose={() => setCitationModal(null)}
      />
    </>
  );
}
