import { useEffect } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { useAuthStore } from "@/stores/auth";
import { api } from "@/api/client";
import { Layout } from "@/components/layout/Layout";
import type { User } from "@/types";

function applyTheme(themeName: string | undefined) {
  const html = document.documentElement;
  if (themeName === "light") {
    html.classList.add("light-theme");
  } else {
    html.classList.remove("light-theme");
  }
}

function applyBoostVisibility(on: boolean | undefined) {
  document.documentElement.classList.toggle("boost-visibility", !!on);
}
import { Login } from "@/pages/Login";
import { Register } from "@/pages/Register";
import { VerifyEmail } from "@/pages/VerifyEmail";
import { ForgotPassword } from "@/pages/ForgotPassword";
import { ResetPassword } from "@/pages/ResetPassword";
import { Dashboard } from "@/pages/Dashboard";
import { Libraries } from "@/pages/Libraries";
import { LibraryNew } from "@/pages/LibraryNew";
import { LibraryDetail } from "@/pages/LibraryDetail";
import { TeachingBoard } from "@/pages/TeachingBoard";
import { UnratedLearning } from "@/pages/UnratedLearning";
import { PublicTeachingBoard } from "@/pages/PublicTeachingBoard";
import { PublicLearn } from "@/pages/PublicLearn";
import { PracticeBoard } from "@/pages/PracticeBoard";
import { Stats } from "@/pages/Stats";
import { MyGames } from "@/pages/MyGames";
import { Public } from "@/pages/Public";
import { PublicLibraryDetail } from "@/pages/PublicLibraryDetail";
import { Settings } from "@/pages/Settings";
import { Admin } from "@/pages/Admin";

function RequireAuth({ children }: { children: JSX.Element }) {
  const token = useAuthStore((s) => s.accessToken);
  const user = useAuthStore((s) => s.user);
  const setUser = useAuthStore((s) => s.setUser);

  useEffect(() => {
    if (token && !useAuthStore.getState().user) {
      api<User>("/auth/me").then((userData) => {
        setUser(userData);
        applyTheme(userData.theme);
        applyBoostVisibility(userData.boost_visibility);
      }).catch(() => {});
    }
  }, [token, setUser]);

  useEffect(() => {
    if (user) {
      applyTheme(user.theme);
      applyBoostVisibility(user.boost_visibility);
    }
  }, [user?.theme, user?.boost_visibility]);

  if (!token) return <Navigate to="/login" replace />;
  return children;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route path="/verify-email" element={<VerifyEmail />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/reset-password" element={<ResetPassword />} />
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
        <Route path="/libraries/:id/unrated" element={<UnratedLearning />} />
        <Route path="/practice" element={<PracticeBoard />} />
        <Route path="/practice/unrated" element={<PracticeBoard />} />
        <Route path="/stats" element={<Stats />} />
        <Route path="/games" element={<MyGames />} />
        <Route path="/public" element={<Public />} />
        <Route path="/public/:id" element={<PublicLibraryDetail />} />
        <Route path="/public/:id/teach" element={<PublicTeachingBoard />} />
        <Route path="/public/:id/learn" element={<PublicLearn />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/admin" element={<Admin />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
