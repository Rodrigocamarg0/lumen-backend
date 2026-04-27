import AuthScreen from "../components/AuthScreen.jsx";
import LogoFlame from "../components/LogoFlame.jsx";
import TermsModal from "../components/TermsModal.jsx";
import { useAuth } from "./useAuth.js";

export function AuthGate({ children }) {
  const { loading, user } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-950 text-white flex items-center justify-center">
        <div className="flex items-center gap-3 text-sm text-gray-300">
          <LogoFlame className="w-7 h-7" />
          Restaurando sessão...
        </div>
      </div>
    );
  }

  if (!user) return <AuthScreen />;

  if (!user.user_metadata?.terms_accepted_at) return <TermsModal />;

  return children;
}
