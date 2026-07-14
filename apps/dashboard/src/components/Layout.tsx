import { Link, Navigate, Outlet } from "react-router-dom";
import { useAuthStore } from "../stores/auth";

export function Layout() {
  const { token, orgName, logout } = useAuthStore();
  if (!token) {
    return <Navigate to="/login" replace />;
  }
  return (
    <div className="min-h-screen bg-zinc-50 text-zinc-900">
      <header className="border-b border-zinc-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3">
          <Link to="/" className="text-lg font-semibold tracking-tight">
            Slate
          </Link>
          <div className="flex items-center gap-4 text-sm text-zinc-600">
            <span>{orgName}</span>
            <button onClick={logout} className="hover:text-zinc-900">
              Sign out
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-6 py-8">
        <Outlet />
      </main>
    </div>
  );
}
