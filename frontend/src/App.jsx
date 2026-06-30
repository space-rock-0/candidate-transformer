import React, { useState } from "react";
import SourceTimeline from "./components/SourceTimeline.jsx";
import SourceInputPanel from "./components/SourceInputPanel.jsx";
import ProfileDossier from "./components/ProfileDossier.jsx";

const API_BASE = import.meta.env.VITE_API_BASE || "/api";

export default function App() {
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleSubmit = async (payload) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/transform/json`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const detail = await res.text();
        throw new Error(detail || `Request failed with status ${res.status}`);
      }
      const data = await res.json();
      setProfile(data);
    } catch (err) {
      setError(err.message || "Something went wrong building the profile.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: 1180, margin: "0 auto", padding: "40px 32px 80px" }}>
      <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/tabler-icons/2.47.0/tabler-icons.min.css" />

      <header style={{ marginBottom: 36 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
          <i className="ti ti-fingerprint" style={{ fontSize: 20, color: "var(--teal)" }} aria-hidden="true" />
          <p
            style={{
              margin: 0,
              fontSize: 12.5,
              fontWeight: 600,
              letterSpacing: "0.06em",
              textTransform: "uppercase",
              color: "var(--teal)",
            }}
          >
            CandidateTransformer
          </p>
        </div>
        <h1
          style={{
            margin: "0 0 8px",
            fontFamily: "var(--font-display)",
            fontWeight: 500,
            fontSize: 36,
            maxWidth: 640,
          }}
        >
          One trustworthy profile, stitched from every source.
        </h1>
        <p style={{ margin: 0, fontSize: 14.5, color: "var(--slate-dim)", maxWidth: 560 }}>
          Honestly empty beats wrong but confident. Enter candidate data from any combination of
          sources below — every merged field keeps its provenance and a visible confidence score.
        </p>
      </header>

      <div style={{ marginBottom: 32 }}>
        <SourceInputPanel onSubmit={handleSubmit} loading={loading} />
      </div>

      {error && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            padding: "12px 16px",
            borderRadius: "var(--radius)",
            background: "rgba(255,107,74,0.1)",
            border: "1px solid rgba(255,107,74,0.35)",
            marginBottom: 24,
            color: "var(--coral)",
            fontSize: 13.5,
          }}
        >
          <i className="ti ti-x" style={{ fontSize: 16 }} aria-hidden="true" />
          {error}
        </div>
      )}

      <div style={{ display: "flex", gap: 32, alignItems: "flex-start" }}>
        <SourceTimeline sourcesUsed={profile?.sources_used || []} />
        <ProfileDossier profile={profile} />
      </div>
    </div>
  );
}
