import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import FlameIcon from "./FlameIcon.jsx";
import CitationModal from "./CitationModal.jsx";

/* ─── Content parser ────────────────────────────────────── */

/**
 * Splits raw streamed content into { reasoning, answer }.
 * Handles partial states while the reasoning block is still being written.
 */
function parseContent(raw) {
  const START = "<|channel>thought";
  const END = "<channel|>";

  if (!raw.startsWith(START)) {
    return { reasoning: null, answer: raw };
  }

  const endIdx = raw.indexOf(END);
  if (endIdx === -1) {
    // Still streaming the reasoning block
    return { reasoning: raw.slice(START.length).trimStart(), answer: null };
  }

  return {
    reasoning: raw.slice(START.length, endIdx).trim(),
    answer: raw.slice(endIdx + END.length).trimStart(),
  };
}

/**
 * Rewrites citation labels found in text to markdown links:
 *   [L.E. Q.1] → [L.E. Q.1](citation://0)
 * so ReactMarkdown's `a` renderer can turn them into buttons.
 */
function linkifyCitations(text, citations) {
  if (!citations?.length || !text) return text ?? "";

  const labelToIdx = {};
  citations.forEach((c, i) => {
    labelToIdx[c.label] = i;
  });

  // Match [...] but avoid already-linked markdown syntax [text](url)
  return text.replace(/\[([^\]]+)\](?!\()/g, (match, label) => {
    if (label in labelToIdx) {
      return `[${label}](citation://${labelToIdx[label]})`;
    }
    return match;
  });
}

/* ─── Markdown renderer ─────────────────────────────────── */

function MarkdownContent({ content, citations, onCitationClick }) {
  const processed = linkifyCitations(content, citations);

  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        p: ({ children }) => (
          <p className="mb-2 last:mb-0 leading-relaxed">{children}</p>
        ),
        strong: ({ children }) => (
          <strong className="font-semibold text-gray-900 dark:text-gray-100">
            {children}
          </strong>
        ),
        em: ({ children }) => <em className="italic">{children}</em>,
        h1: ({ children }) => (
          <h1 className="text-base font-bold mb-2 mt-4 first:mt-0 text-gray-900 dark:text-gray-100">
            {children}
          </h1>
        ),
        h2: ({ children }) => (
          <h2 className="text-sm font-bold mb-2 mt-3 first:mt-0 text-gray-900 dark:text-gray-100">
            {children}
          </h2>
        ),
        h3: ({ children }) => (
          <h3 className="text-sm font-semibold mb-1.5 mt-2 first:mt-0 text-gray-900 dark:text-gray-100">
            {children}
          </h3>
        ),
        ul: ({ children }) => (
          <ul className="list-disc pl-4 mb-2 space-y-0.5">{children}</ul>
        ),
        ol: ({ children }) => (
          <ol className="list-decimal pl-4 mb-2 space-y-0.5">{children}</ol>
        ),
        li: ({ children }) => <li className="leading-relaxed">{children}</li>,
        blockquote: ({ children }) => (
          <blockquote className="border-l-2 border-orange-400/60 pl-3 my-2 text-gray-600 dark:text-gray-400 italic">
            {children}
          </blockquote>
        ),
        pre: ({ children }) => (
          <pre className="bg-gray-100 dark:bg-gray-800 p-3 rounded-lg my-2 overflow-x-auto text-xs font-mono">
            {children}
          </pre>
        ),
        code: ({ children, className }) => {
          // Block code is wrapped in <pre> by remark; inline code has no className
          if (!className) {
            return (
              <code className="bg-gray-100 dark:bg-gray-800 px-1 py-0.5 rounded text-xs font-mono">
                {children}
              </code>
            );
          }
          return <code className={className}>{children}</code>;
        },
        a: ({ href, children }) => {
          if (href?.startsWith("citation://")) {
            const idx = parseInt(href.slice("citation://".length), 10);
            const citation = citations?.[idx];
            return (
              <button
                onClick={() => citation && onCitationClick(citation)}
                className="inline text-orange-500 hover:underline cursor-pointer text-[0.8em] font-medium align-baseline"
                title={citation?.excerpt ?? citation?.label}
              >
                {children}
              </button>
            );
          }
          return (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-orange-500 hover:underline"
            >
              {children}
            </a>
          );
        },
      }}
    >
      {processed}
    </ReactMarkdown>
  );
}

/* ─── Reasoning accordion ───────────────────────────────── */

function ReasoningAccordion({ reasoning, isStreaming }) {
  const [isOpen, setIsOpen] = useState(true);
  const userToggled = useRef(false);

  // Auto-collapse when streaming finishes, unless user manually toggled
  useEffect(() => {
    if (!isStreaming && !userToggled.current) {
      setIsOpen(false);
    }
  }, [isStreaming]);

  const handleToggle = () => {
    userToggled.current = true;
    setIsOpen((v) => !v);
  };

  if (!reasoning) return null;

  return (
    <div className="mb-3 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
      <button
        onClick={handleToggle}
        className="w-full flex items-center justify-between px-3 py-2 text-left
                   bg-gray-50 dark:bg-gray-800/60 hover:bg-gray-100 dark:hover:bg-gray-800
                   transition-colors duration-150"
      >
        <span className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
          <svg
            className="w-3.5 h-3.5 text-orange-400"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"
            />
          </svg>
          Raciocínio
          {isStreaming && (
            <span className="flex gap-0.5 ml-1">
              <span className="w-1 h-1 bg-orange-400 rounded-full typing-dot" />
              <span className="w-1 h-1 bg-orange-400 rounded-full typing-dot" />
              <span className="w-1 h-1 bg-orange-400 rounded-full typing-dot" />
            </span>
          )}
        </span>
        <svg
          className={`w-3.5 h-3.5 text-gray-400 transition-transform duration-200 ${isOpen ? "rotate-180" : ""}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M19 9l-7 7-7-7"
          />
        </svg>
      </button>

      {isOpen && (
        <div
          className="px-3 py-2.5 bg-white dark:bg-gray-900/40 border-t border-gray-200 dark:border-gray-700
                        text-[11px] text-gray-500 dark:text-gray-500 leading-relaxed whitespace-pre-wrap
                        max-h-64 overflow-y-auto font-mono"
        >
          {reasoning}
        </div>
      )}
    </div>
  );
}

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

  const { reasoning, answer } = parseContent(msg.content);
  const isReasoningOnly = reasoning !== null && !answer;

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
            <>
              {reasoning !== null && (
                <ReasoningAccordion
                  reasoning={reasoning}
                  isStreaming={!!msg.streaming}
                />
              )}

              {isReasoningOnly ? (
                // Still streaming reasoning — show a subtle placeholder
                <p className="text-gray-400 dark:text-gray-600 text-xs italic">
                  Elaborando resposta…
                </p>
              ) : (
                <MarkdownContent
                  content={answer ?? msg.content}
                  citations={msg.citations}
                  onCitationClick={onCitationClick}
                />
              )}
            </>
          )}

          {!msg.streaming && (
            <>
              <Citations
                citations={msg.citations}
                onCitationClick={onCitationClick}
              />
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
