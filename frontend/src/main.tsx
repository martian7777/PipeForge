import React from "react";
import ReactDOM from "react-dom/client";
import { createBrowserRouter, Navigate, RouterProvider, useLocation } from "react-router-dom";
import App from "./App";
import { AuthProvider, useAuth } from "./auth";
import UploadPage from "./pages/UploadPage";
import DatasetDetailPage from "./pages/DatasetDetailPage";
import RunEdaPage from "./pages/RunEdaPage";
import AgentSettingsPage from "./pages/AgentSettingsPage";
import AdminPage from "./pages/AdminPage";
import AuthCallbackPage from "./pages/AuthCallbackPage";
import LoginPage from "./pages/LoginPage";
import LandingPage from "./pages/LandingPage";
import "./styles.css";

/** The workspace shell, or the public landing page for visitors who are not signed in.
 *
 * Only "/" falls back to the landing page -- a signed-out visitor who lands deeper
 * (a shared /runs/:id link, say) still goes to the login screen, so nothing that used
 * to require auth stops requiring it.
 */
function Shell() {
  const { user, loading } = useAuth();
  const { pathname } = useLocation();
  if (loading) return <div className="container spinner">Loading…</div>;
  if (!user) return pathname === "/" ? <LandingPage /> : <Navigate to="/login" replace />;
  return <App />;
}

/** Route guard for admin-only screens. The backend enforces this too; this is UX. */
function RequireAdmin({ children }: { children: React.ReactNode }) {
  const { isAdmin, loading } = useAuth();
  if (loading) return <div className="container spinner">Loading…</div>;
  if (!isAdmin) return <Navigate to="/" replace />;
  return <>{children}</>;
}

const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  { path: "/auth/callback", element: <AuthCallbackPage /> },
  {
    path: "/",
    element: <Shell />,
    children: [
      { index: true, element: <UploadPage /> },
      { path: "datasets/:id", element: <DatasetDetailPage /> },
      { path: "runs/:id", element: <RunEdaPage /> },
      { path: "settings/agents", element: <AgentSettingsPage /> },
      {
        path: "admin",
        element: (
          <RequireAdmin>
            <AdminPage />
          </RequireAdmin>
        ),
      },
    ],
  },
]);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <AuthProvider>
      <RouterProvider router={router} />
    </AuthProvider>
  </React.StrictMode>
);
