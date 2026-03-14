import {
  Link,
  Outlet,
  createRootRoute,
  createRoute,
  createRouter
} from "@tanstack/react-router";

import { HomePage } from "@/routes/home";
import { LoginPage } from "@/routes/login";
import { ResultPage } from "@/routes/result";

function AppShell() {
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
          <Link to="/login" className="nav-link">
            Login
          </Link>
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
  component: HomePage
});

const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/login",
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
  defaultPreload: "intent"
});

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
