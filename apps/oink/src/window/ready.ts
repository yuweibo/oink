/** Commit layout and acknowledge DOM readiness before the window is revealed.
 * Native reveal preserves the transparent gutter and the themed DOM surface. */
export function revealWhenReady(reveal: () => void): () => void {
  let stopped = false;
  let done = false;
  const trigger = () => {
    if (stopped || done) return;
    done = true;
    (window as any).__TAURI_INTERNALS__?.invoke?.('frontend_error', { message: 'revealWhenReady trigger called' });
    document.documentElement.getBoundingClientRect();
    reveal();
  };
  // Fallback in case document.fonts.ready stalls when window is initially hidden
  const timer = setTimeout(trigger, 150);
  // Start font/layout work without requiring a rendering opportunity.
  document.documentElement.getBoundingClientRect();
  void document.fonts.ready.then(() => {
    clearTimeout(timer);
    trigger();
  });
  return () => {
    stopped = true;
    clearTimeout(timer);
  };
}
