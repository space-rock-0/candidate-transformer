import React from "react";
import StitchMeter from "./StitchMeter.jsx";
import FieldCard from "./FieldCard.jsx";

const PRIMARY_FIELDS = ["name", "title", "current_company", "email", "phone", "location"];
const SECONDARY_FIELDS = ["summary", "skills", "years_of_experience", "linkedin", "github", "website", "languages", "top_repos"];

export default function ProfileDossier({ profile }) {
  if (!profile) {
    return (
      <div
        style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          color: "var(--slate)",
          padding: "60px 20px",
          textAlign: "center",
        }}
      >
        <i className="ti ti-fingerprint" style={{ fontSize: 36, marginBottom: 12, color: "var(--line-strong)" }} aria-hidden="true" />
        <p style={{ margin: 0, fontSize: 14, maxWidth: 320 }}>
          Add at least one source on the left, then build the profile to see the merged result here.
        </p>
      </div>
    );
  }

  const f = profile.fields;
  const nameVal = f.name?.value || "Unidentified candidate";

  return (
    <div style={{ flex: 1, minWidth: 0 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 22 }}>
        <div>
          <p
            style={{
              margin: "0 0 6px",
              fontSize: 11,
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              color: "var(--slate)",
            }}
            className="mono"
          >
            {profile.candidate_id}
          </p>
          <h1
            style={{
              margin: 0,
              fontFamily: "var(--font-display)",
              fontWeight: 500,
              fontSize: 32,
              color: "var(--paper)",
            }}
          >
            {nameVal}
          </h1>
          {f.title?.value && (
            <p style={{ margin: "4px 0 0", fontSize: 15, color: "var(--slate-dim)" }}>
              {f.title.value}
              {f.current_company?.value && <> · {f.current_company.value}</>}
            </p>
          )}
        </div>
        <div style={{ textAlign: "right", flexShrink: 0 }}>
          <p style={{ margin: "0 0 6px", fontSize: 11, color: "var(--slate)", textTransform: "uppercase", letterSpacing: "0.06em" }}>
            Overall trust
          </p>
          <StitchMeter confidence={profile.overall_confidence} />
        </div>
      </div>

      {profile.conflicts.length > 0 && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            padding: "10px 14px",
            borderRadius: "var(--radius)",
            background: "rgba(255,107,74,0.08)",
            border: "1px solid rgba(255,107,74,0.3)",
            marginBottom: 20,
          }}
        >
          <i className="ti ti-alert-triangle" style={{ fontSize: 16, color: "var(--coral)" }} aria-hidden="true" />
          <p style={{ margin: 0, fontSize: 13, color: "var(--coral)" }}>
            {profile.conflicts.length} field conflict{profile.conflicts.length > 1 ? "s" : ""} resolved across sources. Rejected
            values are kept for audit — expand any field below to inspect them.
          </p>
        </div>
      )}

      <p
        style={{
          margin: "0 0 10px",
          fontSize: 11,
          letterSpacing: "0.08em",
          textTransform: "uppercase",
          color: "var(--slate)",
        }}
      >
        Core fields
      </p>
      {PRIMARY_FIELDS.map((key) => (
        <FieldCard key={key} fieldKey={key} fieldValue={f[key]} conflicts={profile.conflicts} />
      ))}

      <p
        style={{
          margin: "24px 0 10px",
          fontSize: 11,
          letterSpacing: "0.08em",
          textTransform: "uppercase",
          color: "var(--slate)",
        }}
      >
        Extended fields
      </p>
      {SECONDARY_FIELDS.map((key) => (
        <FieldCard key={key} fieldKey={key} fieldValue={f[key]} conflicts={profile.conflicts} />
      ))}
    </div>
  );
}
