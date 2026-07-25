import React from "react";
import ReactDOM from "react-dom/client";
import { createBrowserRouter, Navigate, RouterProvider } from "react-router-dom";
import App from "./App";
import { AuthProvider, useAuth } from "./auth";
import UploadPage from "./pages/UploadPage";
import DatasetDetailPage from "./pages/DatasetDetailPage";
import RunEdaPage from "./pages/RunEdaPage";
import AgentSettingsPage from "./pages/AgentSettingsPage";
import LoginPage from "./pages/LoginPage";
import "./styles.css";

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="container spinner">Loading…</div>;
  if (!user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  {
    path: "/",
    element: (
      <RequireAuth>
        <App />
      </RequireAuth>
    ),
    children: [
      { index: true, element: <UploadPage /> },
      { path: "datasets/:id", element: <DatasetDetailPage /> },
      { path: "runs/:id", element: <RunEdaPage /> },
      { path: "settings/agents", element: <AgentSettingsPage /> },
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
