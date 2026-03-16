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

import { ActiveTasksPage } from "@/routes/active-tasks";
import { HomePage } from "@/routes/home";
import { LoginPage } from "@/routes/login";
import { ResultPage } from "@/routes/result";
import { ResultsHistoryPage } from "@/routes/results-history";
import { getSession, logout } from "@/shared/api/client";
import { Button } from "@/shared/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/shared/ui/card";

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
    <div className="min-h-screen px-4 py-6 sm:px-6">
      <header
        data-glass="true"
        className="mx-auto mb-5 flex max-w-6xl flex-col gap-4 rounded-[calc(var(--radius)+8px)] border border-white/10 bg-background/70 px-4 py-4 shadow-xl backdrop-blur-xl md:flex-row md:items-center md:justify-between"
      >
        <div className="space-y-1">
          <p className="compact-label">KT30</p>
          <Link to="/" className="font-heading text-xl font-semibold tracking-tight text-foreground sm:text-2xl">
            Анализатор технических заданий
          </Link>
        </div>
        <nav className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
          <Button asChild variant="ghost" size="sm">
            <Link to="/">Новый анализ</Link>
          </Button>
          <Button asChild variant="ghost" size="sm">
            <Link to="/tasks">Активные работы</Link>
          </Button>
          <Button asChild variant="ghost" size="sm">
            <Link to="/results">История результатов</Link>
          </Button>
          {authEnabled ? (
            authenticated ? (
              <Button variant="ghost" size="sm" onClick={() => void logoutMutation.mutateAsync()} disabled={logoutMutation.isPending}>
                {logoutMutation.isPending ? "Выходим..." : "Выйти"}
              </Button>
            ) : (
              <Button asChild variant="outline" size="sm">
                <Link to="/login">Войти</Link>
              </Button>
            )
          ) : null}
        </nav>
      </header>
      <main className="mx-auto max-w-6xl">
        <Outlet />
      </main>
    </div>
  );
}

function NotFoundPage() {
  return (
    <Card className="border-border/70 bg-card/90">
      <CardHeader>
        <CardTitle className="text-2xl">Страница не найдена</CardTitle>
        <CardDescription>Запрошенный маршрут пока недоступен в новом интерфейсе.</CardDescription>
      </CardHeader>
      <CardContent>
        <Button asChild>
          <Link to="/">На главную</Link>
        </Button>
      </CardContent>
    </Card>
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

const activeTasksRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tasks",
  component: ActiveTasksPage
});

const resultsHistoryRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/results",
  component: ResultsHistoryPage
});

const resultRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/results/$resultId",
  component: ResultPage
});

const routeTree = rootRoute.addChildren([indexRoute, loginRoute, activeTasksRoute, resultsHistoryRoute, resultRoute]);

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
