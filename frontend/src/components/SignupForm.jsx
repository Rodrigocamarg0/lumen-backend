import { useState } from "react";
import { useAuth } from "../auth/useAuth.js";

export default function SignupForm() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [status, setStatus] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const { signUpWithPassword } = useAuth();

  async function handleSubmit(event) {
    event.preventDefault();
    setStatus("");
    setSubmitting(true);
    const { error } = await signUpWithPassword(email, password);
    if (!error) {
      setStatus(
        "Conta criada. Verifique seu e-mail se a confirmação estiver ativa.",
      );
    }
    setSubmitting(false);
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <label className="block">
        <span className="text-sm text-stone-300">E-mail</span>
        <input
          type="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          required
          autoComplete="email"
          className="mt-2 w-full rounded-2xl border border-white/10 bg-black/25 px-4 py-3 text-white placeholder:text-stone-500 focus:border-orange-300 focus:outline-none"
          placeholder="voce@exemplo.com"
        />
      </label>

      <label className="block">
        <span className="text-sm text-stone-300">Senha</span>
        <input
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          required
          minLength={6}
          autoComplete="new-password"
          className="mt-2 w-full rounded-2xl border border-white/10 bg-black/25 px-4 py-3 text-white placeholder:text-stone-500 focus:border-orange-300 focus:outline-none"
          placeholder="Mínimo de 6 caracteres"
        />
      </label>

      <button
        type="submit"
        disabled={submitting}
        className="w-full rounded-2xl bg-orange-500 px-4 py-3 text-sm font-semibold text-white hover:bg-orange-400 disabled:cursor-not-allowed disabled:opacity-60 transition"
      >
        {submitting ? "Criando conta..." : "Criar conta"}
      </button>

      {status && <p className="text-sm text-orange-100">{status}</p>}
    </form>
  );
}
