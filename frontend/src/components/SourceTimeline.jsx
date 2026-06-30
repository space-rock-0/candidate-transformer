import React from "react";

const SOURCE_META = {
  ats_json: { label: "ATS record", icon: "ti-database", group: "Structured" },
  recruiter_csv: { label: "Recruiter CSV", icon: "ti-table", group: "Structured" },
  resume: { label: "Resume", icon: "ti-file-text", group: "Unstructured" },
  github: { label: "GitHub profile", icon: "ti-brand-github", group: "Unstructured" },
  linkedin: { label: "LinkedIn profile", icon: "ti-brand-linkedin", group: "Unstructured" },
  recruiter_notes: { label: "Recruiter notes", icon: "ti-notes", group: "Unstructured" },
};

const PRIORITY_ORDER = [
  "ats_json",
  "recruiter_csv",
  "resume",
  "linkedin",
  "github",
  "recruiter_notes",
];

export default function SourceTimeline({ sourcesUsed = [] }) {
  const ordered = PRIORITY_ORDER.filter((s) => sourcesUsed.includes(s));

  return (
    <aside
      style={{
        width: 220,
        flexShrink: 0,
        paddingRight: 28,
        borderRight: "1px solid var(--line)",
      }}
    >
      <p
        style={{
          margin: "0 0 4px",
          fontSize: 11,
          letterSpacing: "0.08em",
          textTransform: "uppercase",
          color: "var(--slate)",
        }}
      >
        Sources ingested
      </p>
      <p style={{ margin: "0 0 24px", fontSize: 12, color: "var(--slate-dim)" }}>
        Ordered by trust priority — higher entries win on conflict.
      </p>

      <div style={{ position: "relative" }}>
        <div
          style={{
            position: "absolute",
            left: 11,
            top: 8,
            bottom: 8,
            width: 1,
            background: "var(--line)",
          }}
        />
        {ordered.length === 0 && (
          <p style={{ fontSize: 13, color: "var(--slate)" }}>No sources yet.</p>
        )}
        {ordered.map((s, i) => {
          const meta = SOURCE_META[s] || { label: s, icon: "ti-file", group: "Other" };
          return (
            <div
              key={s}
              style={{
                position: "relative",
                display: "flex",
                alignItems: "center",
                gap: 12,
                marginBottom: 18,
              }}
            >
              <div
                style={{
                  width: 24,
                  height: 24,
                  borderRadius: "50%",
                  background: "var(--ink-2)",
                  border: "1px solid var(--teal)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  zIndex: 1,
                  flexShrink: 0,
                }}
              >
                <i className={`ti ${meta.icon}`} style={{ fontSize: 13, color: "var(--teal)" }} aria-hidden="true" />
              </div>
              <div>
                <p style={{ margin: 0, fontSize: 13, fontWeight: 500 }}>{meta.label}</p>
                <p style={{ margin: 0, fontSize: 11, color: "var(--slate)" }}>{meta.group}</p>
              </div>
            </div>
          );
        })}
      </div>
    </aside>
  );
}
