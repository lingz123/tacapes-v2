import { ReactElement } from 'react';
import { render, type RenderOptions } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, type MemoryRouterProps } from 'react-router-dom';

/**
 * Wraps `render()` with the same providers `main.tsx` mounts: a fresh
 * QueryClient per test (so caches don't leak between cases) and a
 * MemoryRouter pre-loaded with whatever route the test wants to exercise.
 *
 * Retries are disabled so a failing fetcher fails the test immediately
 * instead of swallowing the error in a retry storm.
 */
export function renderWithProviders(
  ui: ReactElement,
  options: {
    routerProps?: MemoryRouterProps;
    queryClient?: QueryClient;
  } & RenderOptions = {},
) {
  const queryClient =
    options.queryClient ??
    new QueryClient({
      defaultOptions: {
        queries: { retry: false, gcTime: 0, staleTime: 0 },
        mutations: { retry: false },
      },
    });
  const initialEntries = options.routerProps?.initialEntries ?? ['/'];
  return {
    queryClient,
    ...render(ui, {
      wrapper: ({ children }) => (
        <QueryClientProvider client={queryClient}>
          <MemoryRouter
            initialEntries={initialEntries}
            future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
          >
            {children}
          </MemoryRouter>
        </QueryClientProvider>
      ),
      ...options,
    }),
  };
}
