# Bug Daddy Frontend

This frontend is a Next.js App Router application exported as static HTML for deployment compatibility.

## Commands

```bash
npm run dev
npm run lint
npm run build
```

## Structure

- `src/app` contains route entrypoints for `/`, `/dashboard`, `/login`, and `/reset`.
- `src/components` contains the migrated React UI for auth, dashboard, issues, admin, toasts, and execution graph modal.
- `src/lib` contains API, auth storage, and shared TypeScript types.

## Compatibility

The app keeps the existing localStorage keys and backend API contract. `next.config.ts` uses `output: "export"`, so `npm run build` emits static files in `out/`, including `dashboard.html`, `login.html`, and `reset.html` for existing static-host links.

The API base remains:

- `http://localhost:8000` on localhost
- `window.location.origin + "/api"` elsewhere
