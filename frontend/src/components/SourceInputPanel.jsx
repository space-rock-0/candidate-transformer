import React, { useState } from "react";

const TABS = [
  { key: "csv", label: "Recruiter CSV", icon: "ti-table" },
  { key: "ats", label: "ATS JSON", icon: "ti-database" },
  { key: "github", label: "GitHub", icon: "ti-brand-github" },
  { key: "resume", label: "Resume text", icon: "ti-file-text" },
  { key: "notes", label: "Recruiter notes", icon: "ti-notes" },
];

const PLACEHOLDERS = {
  csv: "name,email,phone,current_company,title\nJane Doe,jane@corp.com,9876543210,Acme,Engineer",
  ats: `{\n  "full_name": "Jane Doe",\n  "contact_email": "jane@corp.com",\n  "employer": "Acme",\n  "job_title": "Engineer",\n  "skills_list": ["Python", "FastAPI"]\n}`,
  github: "octocat",
  resume: "Paste extracted resume text here…",
  notes: "Free-text recruiter notes about the candidate…",
};

export default function SourceInputPanel({ onSubmit, loading }) {
  const [active, setActive] = useState("csv");
  const [values, setValues] = useState({ csv: "", ats: "", github: "", resume: "", notes: "" });

  const update = (key, val) => setValues((v) => ({ ...v, [key]: val }));

  const handleSubmit = () => {
    let csv_row = null;
    if (values.csv.trim()) {
      const lines = values.csv.trim().split("\n");
      if (lines.length >= 2) {
        const headers = lines[0].split(",").map((h) => h.trim());
        const data = lines[1].split(",").map((d) => d.trim());
        csv_row = Object.fromEntries(headers.map((h, i) => [h, data[i] || ""]));
      }
    }

    let ats_blob = null;
    if (values.ats.trim()) {
      try {
        ats_blob = JSON.parse(values.ats);
      } catch {
        alert("ATS JSON is not valid JSON.");
        return;
      }
    }

    onSubmit({
      csv_row,
      ats_blob,
      github_url: values.github.trim() || null,
      resume_text: values.resume.trim() || null,
      recruiter_notes: values.notes.trim() || null,
    });
  };

  const anyFilled = Object.values(values).some((v) => v.trim());

  return (
    <div
      style={{
        background: "var(--ink-2)",
        border: "1px solid var(--line)",
        borderRadius: "var(--radius-lg)",
        padding: 20,
      }}
    >
      <div style={{ display: "flex", gap: 6, marginBottom: 16, flexWrap: "wrap" }}>
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setActive(t.key)}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              padding: "7px 12px",
              borderRadius: 999,
              border: "1px solid",
              borderColor: active === t.key ? "var(--teal)" : "var(--line-strong)",
              background: active === t.key ? "rgba(34,211,168,0.12)" : "transparent",
              color: active === t.key ? "var(--teal)" : "var(--slate)",
              fontSize: 12.5,
              fontWeight: 500,
              cursor: "pointer",
            }}
          >
            <i className={`ti ${t.icon}`} style={{ fontSize: 14 }} aria-hidden="true" />
            {t.label}
            {values[t.key].trim() && (
              <span style={{ width: 5, height: 5, borderRadius: "50%", background: "var(--teal)" }} />
            )}
          </button>
        ))}
      </div>

      {active === "github" ? (
        <input
          value={values.github}
          onChange={(e) => update("github", e.target.value)}
          placeholder={PLACEHOLDERS.github}
          style={{
            width: "100%",
            padding: "12px 14px",
            borderRadius: "var(--radius)",
            border: "1px solid var(--line-strong)",
            background: "var(--ink)",
            color: "var(--paper)",
            fontSize: 13.5,
            fontFamily: "var(--font-mono)",
          }}
        />
      ) : (
        <textarea
          value={values[active]}
          onChange={(e) => update(active, e.target.value)}
          placeholder={PLACEHOLDERS[active]}
          rows={active === "csv" ? 4 : 8}
          style={{
            width: "100%",
            padding: "12px 14px",
            borderRadius: "var(--radius)",
            border: "1px solid var(--line-strong)",
            background: "var(--ink)",
            color: "var(--paper)",
            fontSize: 13.5,
            fontFamily: active === "ats" ? "var(--font-mono)" : "var(--font-body)",
            resize: "vertical",
          }}
        />
      )}

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 16 }}>
        <p style={{ margin: 0, fontSize: 12, color: "var(--slate)" }}>
          At least one structured and one unstructured source recommended.
        </p>
        <button
          onClick={handleSubmit}
          disabled={!anyFilled || loading}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            padding: "10px 18px",
            borderRadius: "var(--radius)",
            border: "none",
            background: anyFilled && !loading ? "var(--teal)" : "var(--line-strong)",
            color: anyFilled && !loading ? "var(--ink)" : "var(--slate)",
            fontSize: 13.5,
            fontWeight: 600,
            cursor: anyFilled && !loading ? "pointer" : "not-allowed",
          }}
        >
          {loading ? (
            <>
              <i className="ti ti-loader-2" style={{ fontSize: 15 }} aria-hidden="true" />
              Stitching profile…
            </>
          ) : (
            <>
              <i className="ti ti-wand" style={{ fontSize: 15 }} aria-hidden="true" />
              Build canonical profile
            </>
          )}
        </button>
      </div>
    </div>
  );
}
