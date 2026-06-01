// Vitest setup. Adds jest-dom matchers like `toBeInTheDocument` to `expect()`
// and starts a shared MSW node server so any test that imports the listener
// from src/test/server can layer per-test handlers via `server.use(...)`.
import '@testing-library/jest-dom/vitest';
import { afterAll, afterEach, beforeAll } from 'vitest';

import { server } from './server';

// jsdom polyfills Radix needs: PointerEvent + ResizeObserver are absent so
// the Dialog and DropdownMenu code paths crash without these shims.
if (!('PointerEvent' in window)) {
  (window as unknown as { PointerEvent: typeof MouseEvent }).PointerEvent = class extends MouseEvent {} as unknown as typeof MouseEvent;
}
if (!('ResizeObserver' in globalThis)) {
  (globalThis as { ResizeObserver?: unknown }).ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}
// Radix scroll-into-view: jsdom doesn't implement it.
if (!HTMLElement.prototype.scrollIntoView) {
  HTMLElement.prototype.scrollIntoView = () => {};
}
// hasPointerCapture used by Radix focus management.
if (!HTMLElement.prototype.hasPointerCapture) {
  HTMLElement.prototype.hasPointerCapture = () => false;
}
if (!HTMLElement.prototype.releasePointerCapture) {
  HTMLElement.prototype.releasePointerCapture = () => {};
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
