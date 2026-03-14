import {
  Link,
  Outlet,
  createRootRoute,
  createRoute,
  createRouter
} from "@tanstack/react-router";
import { startTransition } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";

import { HomePage } from "@/routes/home";
import { LoginPage } from "@/routes/login";
import { ResultPage } from "@/routes/result";
import { getSession, logout } from "@/shared/api/client";

function normalizeRouterBasePath(rawValue: string | undefined) {
  const trimmed = (rawValue ?? "").trim();

  if (!trimmed || trimmed === "/") {
    return "/";
  }

  return `/${trimmed.replace(/^\/+|\/+$/g, "")}`;
}

const homeSearchSchema = z.object({
  taskId: z.preprocess(
    (value) => (typeof value === "string" && value.trim() ? value.trim() : undefined),
    z.string().optional()
  )
});

const loginSearchSchema = z.object({
  legacyError: z.preprocess(
    (value) => (typeof value === "string" && value.trim() ? value.trim() : undefined),
    z.string().optional()
  )
});

function AppShell() {
  const navigate = rootRoute.useNavigate();
  const queryClient = useQueryClient();
  const sessionQuery = useQuery({
    queryKey: ["session"],
    queryFn: getSession
  });
  const logoutMutation = useMutation({
    mutationFn: logout,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["session"] });
      startTransition(() => {
        void navigate({ to: "/login" });
      });
    }
  });
  const authEnabled = sessionQuery.data?.auth_enabled ?? false;
  const authenticated = sessionQuery.data?.authenticated ?? false;

  return (
    <div className="app-shell">
      <header className="app-header">
        <div>
          <p className="eyebrow">KT30</p>
          <Link to="/" className="brand-link">
            Technical Specification Analyzer
          </Link>
        </div>
        <nav className="app-nav">
          <Link to="/" className="nav-link">
            Upload
          </Link>
          {authEnabled ? (
            authenticated ? (
              <button
                type="button"
                className="nav-link nav-button"
                onClick={() => void logoutMutation.mutateAsync()}
                disabled={logoutMutation.isPending}
              >
                {logoutMutation.isPending ? "Signing out..." : "Sign out"}
              </button>
            ) : (
              <Link to="/login" className="nav-link">
                Login
              </Link>
            )
          ) : null}
        </nav>
      </header>
      <main className="app-main">
        <Outlet />
      </main>
    </div>
  );
}

function NotFoundPage() {
  return (
    <div className="panel">
      <h1>Page not found</h1>
      <p>The route you requested is not available in the new frontend yet.</p>
      <Link to="/" className="primary-button">
        Go home
      </Link>
    </div>
  );
}

const rootRoute = createRootRoute({
  component: AppShell,
  notFoundComponent: NotFoundPage
});

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  validateSearch: homeSearchSchema,
  component: HomePage
});

const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/login",
  validateSearch: loginSearchSchema,
  component: LoginPage
});

const resultRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/results/$resultId",
  component: ResultPage
});

const routeTree = rootRoute.addChildren([indexRoute, loginRoute, resultRoute]);

export const router = createRouter({
  routeTree,
  basepath: normalizeRouterBasePath(import.meta.env.BASE_URL),
  defaultPreload: "intent"
});

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
