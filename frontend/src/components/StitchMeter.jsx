import React from "react";

/**
 * StitchMeter — the signature visual element of CandidateTransformer.
 * Renders confidence as a row of small "stitch" ticks, like thread
 * sewing together a seam: a literal nod to "stitching together"
 * fragmented source data into one trustworthy profile.
 */
export default function StitchMeter({ confidence = 0, size = "md" }) {
  const TOTAL_TICKS = 12;
  const filled = Math.round(confidence * TOTAL_TICKS);

  const color =
    confidence >= 0.75 ? "var(--teal)" : confidence >= 0.5 ? "var(--amber)" : "var(--coral)";

  const tickWidth = size === "sm" ? 3 : 4;
  const tickHeight = size === "sm" ? 10 : 14;
  const gap = size === "sm" ? 2 : 3;

  return (
    <div
      style={{ display: "inline-flex", alignItems: "center", gap: 8 }}
      role="img"
      aria-label={`Confidence ${Math.round(confidence * 100)} percent`}
    >
      <div style={{ display: "flex", alignItems: "flex-end", gap }}>
        {Array.from({ length: TOTAL_TICKS }).map((_, i) => (
          <span
            key={i}
            style={{
              display: "block",
              width: tickWidth,
              height: i < filled ? tickHeight : tickHeight * 0.55,
              borderRadius: 1,
              background: i < filled ? color : "var(--line-strong)",
              transform: i < filled ? "translateY(0)" : "translateY(2px)",
              transition: "height 0.2s ease",
            }}
          />
        ))}
      </div>
      <span
        className="mono"
        style={{ fontSize: size === "sm" ? 11 : 12, color, fontWeight: 500, minWidth: 34 }}
      >
        {Math.round(confidence * 100)}%
      </span>
    </div>
  );
}
