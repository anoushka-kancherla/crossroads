import { useLayoutEffect, useRef } from "react";
import { motionMs, prefersReducedMotion } from "./motion";

type Rects = Map<string, DOMRect>;

function measure(container: HTMLElement): Rects {
  const rects: Rects = new Map();
  container.querySelectorAll<HTMLElement>("[data-resort-key]").forEach((el) => {
    rects.set(el.dataset.resortKey!, el.getBoundingClientRect());
  });
  return rects;
}

/** FLIP: put each item back where it was, then let it slide to its new place. Nothing moves under reduced motion. */
export function animateMoves(container: HTMLElement, before: Rects, reduced: boolean, ms = 200) {
  if (reduced) return;
  container.querySelectorAll<HTMLElement>("[data-resort-key]").forEach((el) => {
    const old = before.get(el.dataset.resortKey!);
    if (!old) return;
    const now = el.getBoundingClientRect();
    const dx = old.left - now.left;
    const dy = old.top - now.top;
    if (!dx && !dy) return;
    el.style.transition = "none";
    el.style.transform = `translate(${dx}px, ${dy}px)`;
    requestAnimationFrame(() => {
      el.style.transition = `transform ${ms}ms ease`;
      el.style.transform = "";
    });
  });
}

/** Attach the returned ref to the list container and mark each item with data-resort-key. When `order`
 *  changes, the items slide to their new places. */
export function useResort<T extends HTMLElement>(order: string) {
  const ref = useRef<T>(null);
  const rects = useRef<Rects>(new Map());
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    animateMoves(el, rects.current, prefersReducedMotion(), motionMs("--motion-resort"));
    rects.current = measure(el);
  }, [order]);
  return ref;
}
