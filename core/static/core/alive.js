// Count-up for numbers marked with data-count-up (dashboard KPIs). Respects reduced motion.
document.addEventListener("DOMContentLoaded", () => {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  document.querySelectorAll("[data-count-up]").forEach((el) => {
    const target = parseInt(el.textContent.trim(), 10);
    if (!Number.isFinite(target) || target <= 0) return;
    const duration = Math.min(1200, 400 + target * 40);
    const start = performance.now();
    const tick = (now) => {
      const p = Math.min(1, (now - start) / duration);
      el.textContent = Math.round(target * (1 - Math.pow(1 - p, 3)));
      if (p < 1) requestAnimationFrame(tick);
    };
    el.textContent = "0";
    requestAnimationFrame(tick);
  });
});
