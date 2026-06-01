import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter } from 'react-router-dom';

import { App } from './App';
import { Toaster } from '@/components/ui/sonner';
import './styles/globals.css';

// Single QueryClient for the whole app. Defaults tuned for a local dashboard:
// no aggressive refetch on focus, but stale-while-revalidate on remount so the
// list page is always fresh after a delete/create flow.
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      staleTime: 30_000,
      retry: 1,
    },
  },
});

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter
        future={{
          // Opt into the v7 behaviour now to silence the dev-time warning.
          // We don't rely on legacy splat-relative resolution and the
          // startTransition wrapper is a no-op for our routes today.
          v7_startTransition: true,
          v7_relativeSplatPath: true,
        }}
      >
        <App />
        <Toaster position="bottom-right" richColors closeButton />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
