import "@testing-library/jest-dom/vitest";

// jsdom lacks these; Recharts / framer-motion probe for them.
class RO { observe() {} unobserve() {} disconnect() {} }
(globalThis as any).ResizeObserver ??= RO;
(globalThis as any).matchMedia ??= (q: string) => ({
  matches: false, media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
});
Element.prototype.scrollIntoView ??= () => {};
