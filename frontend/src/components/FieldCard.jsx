import React, { useState } from "react";
import StitchMeter from "./StitchMeter.jsx";
import SourceChip from "./SourceChip.jsx";

const FIELD_LABELS = {
  name: "Name",
  email: "Email",
  phone: "Phone",
  current_company: "Current company",
  title: "Title",
  location: "Location",
  summary: "Summary",
  skills: "Skills",
  years_of_experience: "Years of experience",
  linkedin: "LinkedIn",
  github: "GitHub",
  website: "Website",
  education: "Education",
  languages: "Languages",
  top_repos: "Top repositories",
};

function formatValue(field, value) {
  if (value === null || value === undefined) return "—";
  if (Array.isArray(value)) {
    if (field === "top_repos") {
      return value.map((r) => `${r.name} (${r.stars}★)`).join(", ");
    }
    return value.join(", ");
  }
  return String(value);
}

export default function FieldCard({ fieldKey, fieldValue, conflicts = [] }) {
  const [expanded, setExpanded] = useState(false);
  const label = FIELD_LABELS[fieldKey] || fieldKey;
  const relatedConflicts = conflicts.filter((c) => c.field === fieldKey);
  const hasConflict = relatedConflicts.length > 0;

  if (!fieldValue) {
    return (
      <div
        style={{
          padding: "14px 18px",
          borderRadius: "var(--radius)",
          border: "1px dashed var(--line-strong)",
          marginBottom: 10,
        }}
      >
        <p style={{ margin: 0, fontSize: 12, color: "var(--slate)", fontWeight: 500 }}>{label}</p>
        <p style={{ margin: "4px 0 0", fontSize: 13.5, color: "var(--slate-dim)" }}>
          Honestly empty — not enough signal across sources.
        </p>
      </div>
    );
  }

  return (
    <div
      style={{
        padding: "14px 18px",
        borderRadius: "var(--radius)",
        background: "var(--ink-2)",
        border: hasConflict ? "1px solid rgba(255,107,74,0.35)" : "1px solid var(--line)",
        marginBottom: 10,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
            <p style={{ margin: 0, fontSize: 12, color: "var(--slate)", fontWeight: 500 }}>{label}</p>
            <SourceChip source={fieldValue.source} />
            {hasConflict && (
              <span
                style={{
                  fontSize: 10.5,
                  fontWeight: 500,
                  color: "var(--coral)",
                  letterSpacing: "0.02em",
                }}
              >
                {relatedConflicts.length} conflict{relatedConflicts.length > 1 ? "s" : ""}
              </span>
            )}
          </div>
          <p
            style={{
              margin: 0,
              fontSize: 15.5,
              fontWeight: 500,
              wordBreak: "break-word",
              color: "var(--paper)",
            }}
          >
            {formatValue(fieldKey, fieldValue.value)}
          </p>
        </div>
        <StitchMeter confidence={fieldValue.confidence} size="sm" />
      </div>

      {hasConflict && (
        <button
          onClick={() => setExpanded(!expanded)}
          style={{
            marginTop: 10,
            background: "none",
            border: "none",
            color: "var(--coral)",
            fontSize: 12,
            cursor: "pointer",
            padding: 0,
            display: "flex",
            alignItems: "center",
            gap: 4,
          }}
        >
          <i className={`ti ${expanded ? "ti-chevron-up" : "ti-chevron-down"}`} style={{ fontSize: 14 }} aria-hidden="true" />
          {expanded ? "Hide rejected values" : "Show rejected values"}
        </button>
      )}

      {expanded && hasConflict && (
        <div style={{ marginTop: 10, paddingTop: 10, borderTop: "1px solid var(--line)" }}>
          {relatedConflicts.map((c, i) => (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
              <SourceChip source={c.loser.source} />
              <span
                style={{
                  fontSize: 13,
                  color: "var(--slate-dim)",
                  textDecoration: "line-through",
                  wordBreak: "break-word",
                }}
              >
                {formatValue(fieldKey, c.loser.value)}
              </span>
              <span style={{ fontSize: 11, color: "var(--slate)" }} className="mono">
                {Math.round(c.loser.confidence * 100)}%
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
