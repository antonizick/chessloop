import { Link, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useAuthStore } from "@/stores/auth";
import { practiceApi } from "@/api/practice";

export function Topbar() {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const navigate = useNavigate();
  const token = useAuthStore((s) => s.accessToken);

  const { data: dueCount } = useQuery({
    queryKey: ["due-count"],
    queryFn: () => practiceApi.dueCount(),
    enabled: !!token,
    staleTime: 60_000,
    refetchInterval: 60_000,
    retry: 1,
  });

  const dueTotal = dueCount?.count ?? 0;

  return (
    <header className="border-b border-ink-700 bg-ink-800/60 backdrop-blur">
      <div className="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-2 text-gold-400 hover:text-gold-300">
          <span className="text-xl font-semibold tracking-tight">♞ ChessLoop</span>
        </Link>

        <nav className="flex items-center gap-5 text-sm">
          <Link to="/libraries" className="text-ink-200 hover:text-gold-400">
            Libraries
          </Link>

          {/* Practice link with due-count badge */}
          <Link
            to="/practice"
            className="flex items-center gap-1.5 text-ink-200 hover:text-gold-400"
          >
            Practice
            {dueTotal > 0 && (
              <span className="inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 rounded-full text-[10px] font-bold bg-gold-500 text-ink-900 leading-none">
                {dueTotal > 99 ? "99+" : dueTotal}
              </span>
            )}
          </Link>

          <Link to="/settings" className="text-ink-200 hover:text-gold-400">
            Settings
          </Link>

          {user && (
            <div className="flex items-center gap-3 pl-4 border-l border-ink-700">
              <span className="text-ink-300">{user.username}</span>
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
