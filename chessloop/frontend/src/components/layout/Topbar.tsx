import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useAuthStore } from "@/stores/auth";
import { authApi } from "@/api/auth";

function applyTheme(themeName: string) {
  const html = document.documentElement;
  if (themeName === "light") {
    html.classList.add("light-theme");
  } else {
    html.classList.remove("light-theme");
  }
}

export function Topbar() {
  const user = useAuthStore((s) => s.user);
  const setUser = useAuthStore((s) => s.setUser);
  const logout = useAuthStore((s) => s.logout);
  const navigate = useNavigate();
  const qc = useQueryClient();

  const updateTheme = useMutation({
    mutationFn: (theme: string) =>
      authApi.updatePreferences({ theme }),
    onSuccess: (updatedUser) => {
      setUser(updatedUser);
      applyTheme(updatedUser.theme);
      qc.invalidateQueries({ queryKey: ["me"] });
    },
  });

  const toggleTheme = () => {
    const newTheme = user?.theme === "light" ? "dark" : "light";
    updateTheme.mutate(newTheme);
  };

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
                onClick={toggleTheme}
                disabled={updateTheme.isPending}
                className="text-ink-400 hover:text-ink-200 transition-colors"
                title={`Switch to ${user.theme === "light" ? "dark" : "light"} theme`}
              >
                {user.theme === "light" ? "☀️" : "🌙"}
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
