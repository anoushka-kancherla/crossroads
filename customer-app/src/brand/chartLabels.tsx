import type { ReactElement } from "react";

type LabelProps = { x?: number | string; y?: number | string; index?: number };

/** A direct label drawn once, at the end of a line, so a series can be told apart without its colour. */
export function endLabel(text: string, lastIndex: number) {
  return function EndLabel({ x, y, index }: LabelProps): ReactElement<SVGElement> {
    if (index !== lastIndex) return <g />;
    return (
      <text x={Number(x) + 8} y={Number(y)} dy={4} className="end-label">
        {text}
      </text>
    );
  };
}
