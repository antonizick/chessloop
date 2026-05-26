import { Link, useNavigate } from "react-router-dom";
import { useAuthStore } from "@/stores/auth";

export function Topbar() {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const navigate = useNavigate();

  return (
    <header className="border-b border-ink-700 bg-ink-800/60 backdrop-blur">
      <div className="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-2 text-gold-400 hover:text-gold-300">
          <span className="text-xl font-semibold tracking-tight">♞ ChessLoop</span>
        </Link>

        <nav className="flex items-center gap-5 text-sm">
          {user && (
            <div className="flex items-center gap-3 pl-4 border-l border-ink-700">
              <button
                onClick={() => navigate("/settings")}
                className="text-ink-300 hover:text-gold-400 cursor-pointer transition-colors"
              >
                {user.username}
              </button>
              <button
                className="btn-ghost text-xs"
                onClick={() => {
                  logout();
                  navigate("/login");
                }}
              >
                Logout
              </button>
            </div>
          )}
        </nav>
      </div>
    </header>
  );
}
