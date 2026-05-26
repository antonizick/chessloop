import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { useAuthStore } from "@/stores/auth";
import type { User } from "@/types";

export function useCurrentUser() {
  const setUser = useAuthStore((s) => s.setUser);
  const cachedUser = useAuthStore((s) => s.user);

  return useQuery({
    queryKey: ["me"],
    queryFn: async () => {
      const u = await api<User>("/auth/me");
      setUser(u);
      return u;
    },
    staleTime: 30000,
    initialData: cachedUser ?? undefined,
  });
}
