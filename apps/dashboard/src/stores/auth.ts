import { create } from "zustand";
import { persist } from "zustand/middleware";

/** UI/session state lives in Zustand; server state lives in TanStack Query (§6). */
interface AuthState {
  token: string | null;
  orgName: string | null;
  login: (token: string, orgName: string) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      orgName: null,
      login: (token, orgName) => set({ token, orgName }),
      logout: () => set({ token: null, orgName: null }),
    }),
    { name: "slate-auth" },
  ),
);
