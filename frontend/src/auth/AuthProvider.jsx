import { useEffect, useMemo, useState } from "react";
import { AuthContext } from "./AuthContext.js";
import { supabase } from "../lib/supabase.js";

function normalizeError(error) {
  if (!error) return null;
  return error.message || "Não foi possível concluir a autenticação.";
}

export function AuthProvider({ children }) {
  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(true);
  const [authError, setAuthError] = useState(null);

  useEffect(() => {
    let mounted = true;

    supabase.auth.getSession().then(({ data, error }) => {
      if (!mounted) return;
      setSession(data.session ?? null);
      setAuthError(normalizeError(error));
      setLoading(false);
    });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      setSession(nextSession);
      setAuthError(null);
      setLoading(false);
    });

    return () => {
      mounted = false;
      subscription.unsubscribe();
    };
  }, []);

  const value = useMemo(
    () => ({
      session,
      user: session?.user ?? null,
      accessToken: session?.access_token ?? null,
      loading,
      authError,
      setAuthError,
      async signInWithPassword(email, password) {
        setAuthError(null);
        const { error } = await supabase.auth.signInWithPassword({
          email,
          password,
        });
        if (error) setAuthError(normalizeError(error));
        return { error };
      },
      async signUpWithPassword(email, password) {
        setAuthError(null);
        const { error } = await supabase.auth.signUp({
          email,
          password,
          options: {
            emailRedirectTo:
              import.meta.env.VITE_SUPABASE_REDIRECT_URL ||
              window.location.origin,
          },
        });
        if (error) setAuthError(normalizeError(error));
        return { error };
      },
      async signInWithGoogle() {
        setAuthError(null);
        const { error } = await supabase.auth.signInWithOAuth({
          provider: "google",
          options: {
            redirectTo:
              import.meta.env.VITE_SUPABASE_REDIRECT_URL ||
              window.location.origin,
          },
        });
        if (error) setAuthError(normalizeError(error));
        return { error };
      },
      async resetPassword(email) {
        setAuthError(null);
        const { error } = await supabase.auth.resetPasswordForEmail(email, {
          redirectTo:
            import.meta.env.VITE_SUPABASE_REDIRECT_URL ||
            window.location.origin,
        });
        if (error) setAuthError(normalizeError(error));
        return { error };
      },
      async signOut() {
        setAuthError(null);
        const { error } = await supabase.auth.signOut();
        if (error) setAuthError(normalizeError(error));
        return { error };
      },
    }),
    [authError, loading, session],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
