export const API_BASE = process.env.E2E_API_BASE ?? "http://127.0.0.1:8000";
export const WEB_PORT = process.env.E2E_WEB_PORT ?? "3000";

export const marketingUrl = (path = "/"): string =>
  `http://localhost:${WEB_PORT}${path}`;

export const signupUrl = (path = "/signup"): string =>
  `http://signup.localhost:${WEB_PORT}${path}`;

export const signinUrl = (slug: string, path = "/signin"): string =>
  `http://${slug}.signin.localhost:${WEB_PORT}${path}`;

export const workspaceUrl = (slug: string, path = "/"): string =>
  `http://${slug}.localhost:${WEB_PORT}${path}`;

export const signupHost = `signup.localhost:${WEB_PORT}`;
export const marketingHost = `localhost:${WEB_PORT}`;
