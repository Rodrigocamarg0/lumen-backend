import { useState } from "react";
import LogoFlame from "./LogoFlame.jsx";
import LoginForm from "./LoginForm.jsx";
import SignupForm from "./SignupForm.jsx";
import { useAuth } from "../auth/useAuth.js";

export default function AuthScreen() {
  const [mode, setMode] = useState("login");
  const { authError, signInWithGoogle } = useAuth();

  return (
    <main className="min-h-screen bg-stone-950 text-stone-50 relative overflow-hidden">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_18%_18%,rgba(251,146,60,0.24),transparent_32%),radial-gradient(circle_at_80%_72%,rgba(120,113,108,0.32),transparent_36%)]" />
      <div className="absolute inset-y-0 right-0 w-1/2 bg-gradient-to-l from-orange-500/10 to-transparent" />

      <div className="relative min-h-screen grid lg:grid-cols-[1.1fr_0.9fr]">
        <section className="flex flex-col justify-between px-6 py-7 sm:px-10 lg:px-14">
          <div className="flex items-center gap-3">
            <LogoFlame className="w-8 h-8" />
            <span className="text-lg font-semibold tracking-tight">Lumen</span>
          </div>

          <div className="max-w-2xl py-16 lg:py-0">
            <p className="text-sm uppercase tracking-[0.35em] text-orange-300/80">
              Biblioteca conversacional
            </p>
            <h1 className="mt-5 text-5xl sm:text-6xl lg:text-7xl font-semibold tracking-tight text-balance">
              Converse com as obras sem perder o fio da pesquisa.
            </h1>
            <p className="mt-6 max-w-xl text-base sm:text-lg text-stone-300 leading-8">
              Entre para restaurar suas conversas, manter histórico por conta e
              continuar estudos em qualquer dispositivo.
            </p>
          </div>

          <div className="grid sm:grid-cols-3 gap-6 text-sm text-stone-400 max-w-3xl">
            <div>
              <div className="text-stone-100 font-medium">
                Histórico privado
              </div>
              <p className="mt-1">Sessões vinculadas apenas à sua conta.</p>
            </div>
            <div>
              <div className="text-stone-100 font-medium">Google ou e-mail</div>
              <p className="mt-1">Autenticação gerenciada pelo Supabase.</p>
            </div>
            <div>
              <div className="text-stone-100 font-medium">
                Citações preservadas
              </div>
              <p className="mt-1">Respostas continuam ligadas às fontes.</p>
            </div>
          </div>
        </section>

        <section className="flex items-center px-6 pb-10 sm:px-10 lg:px-14 lg:py-14">
          <div className="w-full max-w-md mx-auto rounded-3xl border border-white/10 bg-white/[0.07] p-6 sm:p-8 shadow-2xl shadow-black/30 backdrop-blur-xl animate-slide-in">
            <div className="flex rounded-full bg-black/20 p-1 text-sm">
              <button
                type="button"
                onClick={() => setMode("login")}
                className={[
                  "flex-1 rounded-full px-4 py-2 transition",
                  mode === "login"
                    ? "bg-white text-stone-950"
                    : "text-stone-300 hover:text-white",
                ].join(" ")}
              >
                Entrar
              </button>
              <button
                type="button"
                onClick={() => setMode("signup")}
                className={[
                  "flex-1 rounded-full px-4 py-2 transition",
                  mode === "signup"
                    ? "bg-white text-stone-950"
                    : "text-stone-300 hover:text-white",
                ].join(" ")}
              >
                Criar conta
              </button>
            </div>

            <button
              type="button"
              onClick={signInWithGoogle}
              className="mt-6 w-full rounded-2xl border border-white/15 px-4 py-3 text-sm font-medium text-white hover:bg-white/10 transition"
            >
              Continuar com Google
            </button>

            <div className="my-6 flex items-center gap-3 text-xs uppercase tracking-[0.25em] text-stone-500">
              <div className="h-px flex-1 bg-white/10" />
              ou
              <div className="h-px flex-1 bg-white/10" />
            </div>

            {mode === "login" ? <LoginForm /> : <SignupForm />}

            {authError && (
              <p className="mt-4 rounded-2xl bg-red-500/10 px-4 py-3 text-sm text-red-200">
                {authError}
              </p>
            )}
          </div>
        </section>
      </div>
    </main>
  );
}
