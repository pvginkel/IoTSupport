// Global type declarations

declare global {
  interface Window {
    __playwright_emitTestEvent?: (event: unknown) => Promise<void> | void
  }
}

export {}
