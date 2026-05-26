import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { librariesApi } from "@/api/libraries";
import { practiceApi } from "@/api/practice";
import { useAuthStore } from "@/stores/auth";

export function Sidebar() {
  const user = useAuthStore((s) => s.user);
  const token = useAuthStore((s) => s.accessToken);
  const location = useLocation();
  const [showNav, setShowNav] = useState(true);
  const { data: libraries = [] } = useQuery({
    queryKey: ["libraries", token],
    queryFn: librariesApi.list,
    enabled: !!token,
    staleTime: 0,
    refetchOnMount: "always",
  });

  const { data: dueCount } = useQuery({
    queryKey: ["due-count"],
    queryFn: () => practiceApi.dueCount(),
    enabled: !!token,
    staleTime: 60_000,
    refetchInterval: 60_000,
    retry: 1,
  });

  const dueTotal = dueCount?.count ?? 0;

  const navItems = [
    { label: "My Opening Libraries", path: "/libraries" },
    { label: "Rated Practice", path: "/practice", badge: dueTotal > 0 ? dueTotal : null },
    { label: "My Stats", path: "/stats" },
    { label: "Public Opening Libraries", path: "/public" },
  ];

  return (
    <aside className="hidden md:flex flex-col w-60 border-r border-ink-700 bg-ink-800/40 p-4 gap-2">
      {/* Main Navigation */}
      <div className="mb-4">
        <button
          onClick={() => setShowNav(!showNav)}
          className="w-full flex items-center justify-between mb-2 px-2 py-1.5 rounded hover:bg-ink-700/50 transition-colors"
        >
          <h2 className="text-xs uppercase tracking-wider text-ink-300">Menu</h2>
          <span className="text-xs text-ink-400">{showNav ? "▼" : "▶"}</span>
        </button>
        {showNav && (
          <ul className="flex flex-col gap-1 text-sm">
            {navItems.map((item) => (
              <li key={item.path}>
                <Link
                  to={item.path}
                  className={`flex items-center justify-between px-2 py-1.5 rounded transition-colors ${
                    location.pathname === item.path || location.pathname.startsWith(item.path + "/")
                      ? "bg-ink-700 text-gold-400"
                      : "text-ink-200 hover:bg-ink-700"
                  }`}
                >
                  <span>{item.label}</span>
                  {item.badge && (
                    <span className="inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 rounded-full text-[10px] font-bold bg-gold-500 text-ink-900 leading-none">
                      {item.badge > 99 ? "99+" : item.badge}
                    </span>
                  )}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* My Libraries Section */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-xs uppercase tracking-wider text-ink-300">My Libraries</h2>
          <Link to="/libraries/new" className="text-xs text-gold-400 hover:text-gold-300">+ New</Link>
        </div>
        <ul className="flex flex-col gap-1 text-sm">
          {libraries?.length === 0 && (
            <li className="text-ink-400 italic">No libraries yet.</li>
          )}
          {libraries?.map((lib) => (
            <li key={lib.id}>
              <Link
                to={`/libraries/${lib.id}`}
                className="block px-2 py-1.5 rounded hover:bg-ink-700 text-ink-200"
              >
                <span className="mr-2 text-gold-400">
                  {lib.color === "white" ? "♔" : lib.color === "black" ? "♚" : "⚭"}
                </span>
                {lib.name}
              </Link>
            </li>
          ))}
        </ul>
      </div>

      {user?.role === "admin" && (
        <div className="mt-auto pt-4 border-t border-ink-700">
          <Link
            to="/admin"
            className="block px-2 py-1.5 rounded text-xs text-ink-400 hover:bg-ink-700 hover:text-gold-400 transition-colors"
          >
            ⚙ Admin panel
          </Link>
        </div>
      )}
    </aside>
  );
}
