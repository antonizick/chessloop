import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { librariesApi } from "@/api/libraries";

export function Sidebar() {
  const { data: libraries } = useQuery({
    queryKey: ["libraries"],
    queryFn: librariesApi.list,
  });

  return (
    <aside className="hidden md:flex flex-col w-60 border-r border-ink-700 bg-ink-800/40 p-4 gap-2">
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
    </aside>
  );
}
