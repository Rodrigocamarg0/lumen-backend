import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import LogoFlame from "./LogoFlame.jsx";
import { supabase } from "../lib/supabase.js";
import { useAuth } from "../auth/useAuth.js";
import { acceptTerms as acceptTermsApi } from "../lib/api.js";

const TERMS_URL = "/terms.md";
const TERMS_VERSION = "1.0";

const markdownComponents = {
  h1: ({ children }) => (
    <h2 className="mt-4 first:mt-0 text-base font-semibold text-stone-100">
      {children}
    </h2>
  ),
  h2: ({ children }) => (
    <h3 className="mt-3 text-sm font-semibold text-stone-100">{children}</h3>
  ),
  h3: ({ children }) => (
    <h4 className="mt-2 text-sm font-medium text-stone-200">{children}</h4>
  ),
  p: ({ children }) => (
    <p className="mt-2 text-stone-300/90 leading-6">{children}</p>
  ),
  ul: ({ children }) => (
    <ul className="mt-2 list-disc pl-5 space-y-1 text-stone-300/90">
      {children}
    </ul>
  ),
  ol: ({ children }) => (
    <ol className="mt-2 list-decimal pl-5 space-y-1 text-stone-300/90">
      {children}
    </ol>
  ),
  li: ({ children }) => <li className="leading-6">{children}</li>,
  strong: ({ children }) => (
    <strong className="font-semibold text-stone-100">{children}</strong>
  ),
  em: ({ children }) => <em className="italic">{children}</em>,
  hr: () => <hr className="my-4 border-white/10" />,
  a: ({ children, href }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-orange-300 hover:text-orange-200 underline-offset-4 hover:underline"
    >
      {children}
    </a>
  ),
};

export default function TermsModal() {
  const { signOut, accessToken } = useAuth();
  const [acceptTerms, setAcceptTerms] = useState(false);
  const [acceptLgpd, setAcceptLgpd] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [terms, setTerms] = useState("");
  const [termsError, setTermsError] = useState(null);
  const [termsLoading, setTermsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const res = await fetch(TERMS_URL, { cache: "no-cache" });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const text = await res.text();
        if (!cancelled) setTerms(text);
      } catch (err) {
        if (!cancelled)
          setTermsError(err.message ?? "Não foi possível carregar os termos.");
      } finally {
        if (!cancelled) setTermsLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  const canAccept = acceptTerms && acceptLgpd && !submitting && !termsError;

  async function handleAccept() {
    if (!canAccept) return;
    setSubmitting(true);
    setError(null);

    try {
      // 1. Server-side audit trail (append-only, tamper-proof)
      await acceptTermsApi(TERMS_VERSION, accessToken);

      // 2. Supabase metadata (UX gate only)
      const acceptedAt = new Date().toISOString();
      const { error: updateError } = await supabase.auth.updateUser({
        data: {
          terms_accepted_at: acceptedAt,
          lgpd_accepted_at: acceptedAt,
          terms_version: TERMS_VERSION,
        },
      });
      if (updateError) {
        throw updateError;
      }
    } catch (err) {
      setError(err.message ?? "Não foi possível registrar sua aceitação.");
      setSubmitting(false);
    }
  }

  async function handleDecline() {
    await signOut();
  }

  return (
    <main
      role="dialog"
      aria-modal="true"
      aria-labelledby="terms-title"
      className="min-h-screen bg-stone-950 text-stone-50 flex items-center justify-center p-4 sm:p-6"
    >
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_18%_18%,rgba(251,146,60,0.18),transparent_32%),radial-gradient(circle_at_82%_72%,rgba(120,113,108,0.28),transparent_36%)]" />

      <div className="relative w-full max-w-2xl rounded-3xl border border-white/10 bg-white/[0.07] p-6 sm:p-8 shadow-2xl shadow-black/40 backdrop-blur-xl animate-slide-in">
        <div className="flex items-center gap-3">
          <LogoFlame className="w-7 h-7" />
          <span className="text-base font-semibold tracking-tight">Lumen</span>
        </div>

        <div className="mt-6">
          <p className="text-xs uppercase tracking-[0.3em] text-orange-300/80">
            Antes de começar
          </p>
          <h1
            id="terms-title"
            className="mt-3 text-2xl sm:text-3xl font-semibold tracking-tight"
          >
            Termos de uso e proteção de dados
          </h1>
          <p className="mt-3 text-sm text-stone-300 leading-6">
            Para criar sua conta na Lumen e iniciar conversas, precisamos do seu
            aceite aos termos de uso e à nossa política de tratamento de dados,
            em conformidade com a Lei Geral de Proteção de Dados (LGPD — Lei nº
            13.709/2018).
          </p>
        </div>

        <div className="mt-5 max-h-72 overflow-y-auto rounded-2xl border border-white/10 bg-black/25 p-4 text-sm leading-6">
          {termsLoading && <p className="text-stone-400">Carregando termos…</p>}
          {termsError && (
            <p className="text-red-200">
              Não foi possível carregar os termos ({termsError}). Tente
              recarregar a página.
            </p>
          )}
          {!termsLoading && !termsError && (
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={markdownComponents}
            >
              {terms}
            </ReactMarkdown>
          )}
        </div>

        <div className="mt-5 space-y-3">
          <label className="flex items-start gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={acceptTerms}
              onChange={(e) => setAcceptTerms(e.target.checked)}
              className="mt-0.5 h-4 w-4 rounded border-white/20 bg-black/30 text-orange-500 focus:ring-orange-400 focus:ring-offset-0"
            />
            <span className="text-sm text-stone-200 leading-6">
              Li e concordo com os{" "}
              <span className="font-medium text-stone-50">termos de uso</span>{" "}
              da Lumen.
            </span>
          </label>

          <label className="flex items-start gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={acceptLgpd}
              onChange={(e) => setAcceptLgpd(e.target.checked)}
              className="mt-0.5 h-4 w-4 rounded border-white/20 bg-black/30 text-orange-500 focus:ring-orange-400 focus:ring-offset-0"
            />
            <span className="text-sm text-stone-200 leading-6">
              Autorizo o tratamento dos meus dados conforme a{" "}
              <span className="font-medium text-stone-50">
                política de privacidade (LGPD)
              </span>
              .
            </span>
          </label>
        </div>

        {error && (
          <p className="mt-4 rounded-2xl bg-red-500/10 px-4 py-3 text-sm text-red-200">
            {error}
          </p>
        )}

        <div className="mt-6 flex flex-col-reverse sm:flex-row sm:items-center sm:justify-end gap-3">
          <button
            type="button"
            onClick={handleDecline}
            disabled={submitting}
            className="rounded-2xl border border-white/15 px-4 py-2.5 text-sm font-medium text-stone-200 hover:bg-white/10 disabled:opacity-50 transition"
          >
            Recusar e sair
          </button>
          <button
            type="button"
            onClick={handleAccept}
            disabled={!canAccept}
            className="rounded-2xl bg-orange-500 px-5 py-2.5 text-sm font-semibold text-white hover:bg-orange-400 disabled:cursor-not-allowed disabled:opacity-60 transition"
          >
            {submitting ? "Registrando..." : "Aceitar e continuar"}
          </button>
        </div>
      </div>
    </main>
  );
}
