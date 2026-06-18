import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { librariesApi } from "@/api/libraries";
import { practiceApi } from "@/api/practice";
import { useAuthStore } from "@/stores/auth";
import { Tooltip } from "@/components/ui/Tooltip";
import { LibrarySelectorModal } from "@/components/layout/LibrarySelectorModal";

const ICON_MAP: Record<string, string> = {
  home: "🏠",
  libraries: "📚",
  "unrated-practice": "🎯",
  "rated-practice": "⭐",
  stats: "📊",
  games: "♟️",
  public: "🌐",
  learning: "📚",
  teaching: "✏️",
};

export function Sidebar() {
  const user = useAuthStore((s) => s.user);
  const token = useAuthStore((s) => s.accessToken);
  const location = useLocation();
  const [showNav, setShowNav] = useState(true);
  const [showLibraries, setShowLibraries] = useState(true);
  const [selectorMode, setSelectorMode] = useState<"learn" | "teach" | null>(null);
  const [isCollapsed, setIsCollapsed] = useState(false);
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
    { label: "Home", path: "/", icon: ICON_MAP.home },
    { label: "My Opening Libraries", path: "/libraries", icon: ICON_MAP.libraries },
    { label: "Unrated Practice", path: "/practice/unrated", badge: null, icon: ICON_MAP["unrated-practice"] },
    { label: "Rated Practice", path: "/practice", badge: dueTotal > 0 ? dueTotal : null, icon: ICON_MAP["rated-practice"] },
    { label: "My Stats", path: "/stats", icon: ICON_MAP.stats },
    { label: "My Games", path: "/games", icon: ICON_MAP.games },
    { label: "Public Opening Libraries", path: "/public", icon: ICON_MAP.public },
  ];

  const sidebarWidth = isCollapsed ? "w-16" : "w-60";

  return (
    <aside className={`hidden md:flex flex-col ${sidebarWidth} border-r border-ink-700 bg-ink-800/40 p-3 gap-2 transition-all duration-300`}>
      {/* Toggle Button */}
      <div className="flex justify-center mb-2">
        <Tooltip text={isCollapsed ? "Expand menu" : "Collapse menu"}>
          <button
            onClick={() => setIsCollapsed(!isCollapsed)}
            className="p-2 rounded hover:bg-ink-700/50 text-ink-300 transition-colors"
            title={isCollapsed ? "Expand menu" : "Collapse menu"}
          >
            {isCollapsed ? "→" : "←"}
          </button>
        </Tooltip>
      </div>

      {/* Main Navigation */}
      <div className="mb-4">
        {!isCollapsed && (
          <button
            onClick={() => setShowNav(!showNav)}
            className="w-full flex items-center justify-between mb-2 px-2 py-1.5 rounded hover:bg-ink-700/50 transition-colors"
          >
            <h2 className="text-xs uppercase tracking-wider text-ink-300">Menu</h2>
            <span className="text-xs text-ink-400">{showNav ? "▼" : "▶"}</span>
          </button>
        )}
        {(showNav || isCollapsed) && (
          <ul className="flex flex-col gap-1 text-sm">
            {/* Home */}
            <li>
              {isCollapsed ? (
                <Tooltip text={navItems[0].label}>
                  <Link
                    to={navItems[0].path}
                    className={`flex items-center justify-center h-10 rounded transition-colors ${
                      location.pathname === navItems[0].path || location.pathname.startsWith(navItems[0].path + "/")
                        ? "bg-ink-700 text-gold-400"
                        : "text-ink-200 hover:bg-ink-700"
                    }`}
                  >
                    <span className="text-lg">{navItems[0].icon}</span>
                  </Link>
                </Tooltip>
              ) : (
                <Link
                  to={navItems[0].path}
                  className={`flex items-center justify-between px-2 py-1.5 rounded transition-colors ${
                    location.pathname === navItems[0].path || location.pathname.startsWith(navItems[0].path + "/")
                      ? "bg-ink-700 text-gold-400"
                      : "text-ink-200 hover:bg-ink-700"
                  }`}
                >
                  <span>{navItems[0].label}</span>
                </Link>
              )}
            </li>

            {/* Learning and Teaching menu items */}
            <li>
              {isCollapsed ? (
                <Tooltip text="Learning: Unrated browsing of opening lines to learn and internalize your opening repertoire.">
                  <button
                    onClick={() => setSelectorMode("learn")}
                    className="w-full flex items-center justify-center h-10 rounded hover:bg-ink-700 text-ink-200 transition-colors"
                  >
                    <span className="text-lg">{ICON_MAP.learning}</span>
                  </button>
                </Tooltip>
              ) : (
                <Tooltip text="Unrated browsing of opening lines to learn and internalize your opening repertoire.">
                  <button
                    onClick={() => setSelectorMode("learn")}
                    className="w-full text-left flex items-center px-2 py-1.5 rounded hover:bg-ink-700 text-ink-200 transition-colors"
                  >
                    <span>📚 Learning</span>
                  </button>
                </Tooltip>
              )}
            </li>
            <li>
              {isCollapsed ? (
                <Tooltip text="Teaching: Train, refine, add and edit opening lines in your opening libraries.">
                  <button
                    onClick={() => setSelectorMode("teach")}
                    className="w-full flex items-center justify-center h-10 rounded hover:bg-ink-700 text-ink-200 transition-colors"
                  >
                    <span className="text-lg">{ICON_MAP.teaching}</span>
                  </button>
                </Tooltip>
              ) : (
                <Tooltip text="Train, refine, add and edit opening lines in your opening libraries.">
                  <button
                    onClick={() => setSelectorMode("teach")}
                    className="w-full text-left flex items-center px-2 py-1.5 rounded hover:bg-ink-700 text-ink-200 transition-colors"
                  >
                    <span>✏️ Teaching</span>
                  </button>
                </Tooltip>
              )}
            </li>

            {/* Rest of nav items */}
            {navItems.slice(1).map((item) => (
              <li key={item.path}>
                {isCollapsed ? (
                  <Tooltip text={item.label + (item.badge ? ` (${item.badge})` : "")}>
                    <Link
                      to={item.path}
                      state={
                        item.path === "/practice/unrated" || item.path === "/practice"
                          ? { restart: true }
                          : undefined
                      }
                      className={`flex items-center justify-center h-10 rounded transition-colors relative ${
                        location.pathname === item.path || location.pathname.startsWith(item.path + "/")
                          ? "bg-ink-700 text-gold-400"
                          : "text-ink-200 hover:bg-ink-700"
                      }`}
                    >
                      <span className="text-lg">{item.icon}</span>
                      {item.badge && (
                        <span className="absolute top-0 right-0 inline-flex items-center justify-center w-5 h-5 rounded-full text-[10px] font-bold bg-gold-500 text-ink-900 leading-none transform translate-x-1 -translate-y-1">
                          {item.badge > 99 ? "99+" : item.badge}
                        </span>
                      )}
                    </Link>
                  </Tooltip>
                ) : (
                  <Link
                    to={item.path}
                    state={
                      item.path === "/practice/unrated" || item.path === "/practice"
                        ? { restart: true }
                        : undefined
                    }
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
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* My Libraries Section */}
      {!isCollapsed && (
        <div>
          <button
            onClick={() => setShowLibraries(!showLibraries)}
            className="w-full flex items-center justify-between mb-2 px-2 py-1.5 rounded hover:bg-ink-700/50 transition-colors"
          >
            <h2 className="text-xs uppercase tracking-wider text-ink-300">My Libraries</h2>
            <span className="text-xs text-ink-400">{showLibraries ? "▼" : "▶"}</span>
          </button>
          {showLibraries && (
            <>
              <Link to="/libraries/new" className="block text-xs text-gold-400 hover:text-gold-300 mb-2 px-2">+ New</Link>
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
            </>
          )}
        </div>
      )}

      {/* Library Selector Modal */}
      {selectorMode && (
        <LibrarySelectorModal
          libraries={libraries || []}
          onClose={() => setSelectorMode(null)}
          mode={selectorMode}
        />
      )}

      {user?.role === "admin" && (
        <div className="mt-auto pt-4 border-t border-ink-700">
          {isCollapsed ? (
            <Tooltip text="Admin panel">
              <Link
                to="/admin"
                className="flex items-center justify-center h-10 rounded text-ink-400 hover:bg-ink-700 hover:text-gold-400 transition-colors"
              >
                <span className="text-lg">⚙</span>
              </Link>
            </Tooltip>
          ) : (
            <Link
              to="/admin"
              className="block px-2 py-1.5 rounded text-xs text-ink-400 hover:bg-ink-700 hover:text-gold-400 transition-colors"
            >
              ⚙ Admin panel
            </Link>
          )}
        </div>
      )}
    </aside>
  );
}
