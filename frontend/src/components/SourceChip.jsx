import React from "react";

const SOURCE_LABELS = {
  ats_json: "ATS",
  recruiter_csv: "CSV",
  resume: "Resume",
  github: "GitHub",
  linkedin: "LinkedIn",
  recruiter_notes: "Notes",
};

export default function SourceChip({ source }) {
  const label = SOURCE_LABELS[source] || source;
  return (
    <span
      className="mono"
      style={{
        display: "inline-block",
        fontSize: 10.5,
        fontWeight: 500,
        letterSpacing: "0.03em",
        textTransform: "uppercase",
        padding: "2px 8px",
        borderRadius: 999,
        background: "var(--ink-2)",
        border: "1px solid var(--line-strong)",
        color: "var(--slate)",
      }}
    >
      {label}
    </span>
  );
}
