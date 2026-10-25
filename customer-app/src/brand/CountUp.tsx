import { useEffect, useRef, useState } from "react";
import { motionMs, prefersReducedMotion } from "./motion";

const NUMBER = /-?\d[\d,]*(\.\d+)?/;

function parts(text: string) {
  const m = NUMBER.exec(text);
  if (!m) return null;
  const decimals = m[1] ? m[1].length - 1 : 0;
  return { start: m.index, end: m.index + m[0].length, n: parseFloat(m[0].replace(/,/g, "")), decimals };
}

/** Shows a figure the server returned. When it changes, the number counts up to the new value; the last
 *  frame is the exact text, so the display never differs from the data. No animation on first render,
 *  under reduced motion, or for text without a number. */
export function CountUp({ value, className }: { value: string; className?: string }) {
  const [shown, setShown] = useState(value);
  const previous = useRef(value);

  useEffect(() => {
    const from = previous.current;
    previous.current = value;
    if (from === value) return;
    const a = parts(from);
    const b = parts(value);
    const duration = motionMs("--motion-count");
    if (prefersReducedMotion() || !a || !b || duration <= 0) {
      setShown(value);
      return;
    }
    const t0 = performance.now();
    let raf = 0;
    const step = (t: number) => {
      const k = (t - t0) / duration;
      if (k >= 1) {
        setShown(value);
        return;
      }
      const n = a.n + (b.n - a.n) * k;
      const text = n.toLocaleString("en-US", { minimumFractionDigits: b.decimals, maximumFractionDigits: b.decimals });
      setShown(value.slice(0, b.start) + text + value.slice(b.end));
      raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [value]);

  return <span className={className}>{prefersReducedMotion() ? value : shown}</span>;
}
