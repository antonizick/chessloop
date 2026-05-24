import { Routes, Route, Navigate } from "react-router-dom";
import { useAuthStore } from "@/stores/auth";
import { Layout } from "@/components/layout/Layout";
import { Login } from "@/pages/Login";
import { Register } from "@/pages/Register";
import { Dashboard } from "@/pages/Dashboard";
import { Libraries } from "@/pages/Libraries";
import { LibraryNew } from "@/pages/LibraryNew";
import { LibraryDetail } from "@/pages/LibraryDetail";
import { TeachingBoard } from "@/pages/TeachingBoard";
import { PracticeBoard } from "@/pages/PracticeBoard";
import { Stats } from "@/pages/Stats";
import { Public } from "@/pages/Public";
import { PublicLibraryDetail } from "@/pages/PublicLibraryDetail";
import { Settings } from "@/pages/Settings";

function RequireAuth({ children }: { children: JSX.Element }) {
  const token = useAuthStore((s) => s.accessToken);
  if (!token) return <Navigate to="/login" replace />;
  return children;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route path="/" element={<Dashboard />} />
        <Route path="/libraries" element={<Libraries />} />
        <Route path="/libraries/new" element={<LibraryNew />} />
        <Route path="/libraries/:id" element={<LibraryDetail />} />
        <Route path="/libraries/:id/teach" element={<TeachingBoard />} />
        <Route path="/practice" element={<PracticeBoard />} />
        <Route path="/stats" element={<Stats />} />
        <Route path="/public" element={<Public />} />
        <Route path="/public/:id" element={<PublicLibraryDetail />} />
        <Route path="/settings" element={<Settings />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
