import React, { useState } from "react";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1";

interface QueryResult {
  answer: string;
  triage_priority: "CRITICAL" | "URGENT" | "ROUTINE" | "UNKNOWN";
  model_used: string;
  sources: { source: string; score: number }[];
  hipaa_compliant: boolean;
  clinical_alert: boolean;
}

const PRIORITY_COLORS: Record<string, string> = {
  CRITICAL: "#dc2626",
  URGENT: "#d97706",
  ROUTINE: "#059669",
  UNKNOWN: "#6b7280",
};

export default function App() {
  const [mode, setMode] = useState<"query" | "triage">("query");
  const [query, setQuery] = useState("");
  const [symptoms, setSymptoms] = useState("");
  const [patientContext, setPatientContext] = useState("");
  const [useClaude, setUseClaude] = useState(true);
  const [result, setResult] = useState<QueryResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const submit = async () => {
    setLoading(true);
    setError("");
    setResult(null);
    try {
      let endpoint = "";
      let body: any = {};
      if (mode === "query") {
        endpoint = "/medical/query";
        body = { query, use_claude: useClaude };
      } else {
        endpoint = "/medical/triage";
        body = { symptoms, patient_context: patientContext || undefined };
      }
      const res = await fetch(`${API_URL}${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      setResult(await res.json());
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ fontFamily: "system-ui", maxWidth: 900, margin: "0 auto", padding: 32 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 8 }}>
        <span style={{ fontSize: 40 }}>🏥</span>
        <div>
          <h1 style={{ margin: 0, color: "#0f172a" }}>HealthBridge AI</h1>
          <p style={{ margin: 0, color: "#64748b" }}>Medical Document Intelligence & Triage Assistant</p>
        </div>
      </div>

      <div style={{ background: "#fef3c7", border: "1px solid #fbbf24", borderRadius: 8, padding: 12, marginBottom: 24, fontSize: 13 }}>
        ⚠️ <strong>For healthcare professional use only.</strong> Not a substitute for clinical judgment or direct patient examination.
      </div>

      {/* Mode Selector */}
      <div style={{ display: "flex", gap: 8, marginBottom: 24 }}>
        {["query", "triage"].map((m) => (
          <button
            key={m}
            onClick={() => setMode(m as any)}
            style={{
              padding: "8px 20px",
              borderRadius: 8,
              border: "2px solid #0f172a",
              background: mode === m ? "#0f172a" : "white",
              color: mode === m ? "white" : "#0f172a",
              fontWeight: 600,
              cursor: "pointer",
              textTransform: "capitalize",
            }}
          >
            {m === "query" ? "📚 Document Query" : "🚨 Triage Assessment"}
          </button>
        ))}
      </div>

      <div style={{ background: "#f8fafc", borderRadius: 12, padding: 24, marginBottom: 24 }}>
        {mode === "query" ? (
          <>
            <label style={{ fontWeight: 600 }}>Clinical Query</label>
            <textarea
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="e.g. What are standard protocols for managing acute MI in elderly patients?"
              rows={4}
              style={{ width: "100%", padding: 10, borderRadius: 8, border: "1px solid #e2e8f0", marginTop: 8, fontSize: 15, boxSizing: "border-box" }}
            />
          </>
        ) : (
          <>
            <label style={{ fontWeight: 600 }}>Presenting Symptoms</label>
            <textarea
              value={symptoms}
              onChange={(e) => setSymptoms(e.target.value)}
              placeholder="e.g. Chest pain radiating to left arm, diaphoresis, shortness of breath, onset 30 minutes ago"
              rows={3}
              style={{ width: "100%", padding: 10, borderRadius: 8, border: "1px solid #e2e8f0", marginTop: 8, marginBottom: 16, fontSize: 15, boxSizing: "border-box" }}
            />
            <label style={{ fontWeight: 600 }}>Patient Context (optional)</label>
            <input
              value={patientContext}
              onChange={(e) => setPatientContext(e.target.value)}
              placeholder="e.g. 65-year-old male, hypertension, diabetes"
              style={{ width: "100%", padding: 10, borderRadius: 8, border: "1px solid #e2e8f0", marginTop: 8, fontSize: 15, boxSizing: "border-box" }}
            />
          </>
        )}

        <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 16 }}>
          <label style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer" }}>
            <input type="checkbox" checked={useClaude} onChange={(e) => setUseClaude(e.target.checked)} />
            Use Claude 3.5 Sonnet
          </label>
          <button
            onClick={submit}
            disabled={loading || (mode === "query" ? !query.trim() : !symptoms.trim())}
            style={{
              padding: "10px 24px",
              background: "#0f172a",
              color: "white",
              border: "none",
              borderRadius: 8,
              fontWeight: 600,
              cursor: "pointer",
              opacity: loading ? 0.6 : 1,
            }}
          >
            {loading ? "Processing..." : mode === "query" ? "🔍 Query" : "🚨 Assess"}
          </button>
        </div>
      </div>

      {error && (
        <div style={{ background: "#fff0f0", border: "1px solid #fca5a5", borderRadius: 8, padding: 16, color: "#dc2626", marginBottom: 16 }}>
          {error}
        </div>
      )}

      {result && (
        <div>
          {result.clinical_alert && (
            <div style={{ background: "#dc2626", color: "white", borderRadius: 8, padding: 12, marginBottom: 16, fontWeight: 600 }}>
              🚨 CLINICAL ALERT – Immediate attention may be required
            </div>
          )}

          <div style={{ display: "flex", gap: 12, marginBottom: 16 }}>
            <div style={{ background: PRIORITY_COLORS[result.triage_priority], color: "white", borderRadius: 8, padding: "8px 16px", fontWeight: 700, fontSize: 15 }}>
              {result.triage_priority}
            </div>
            <div style={{ background: "#e2e8f0", borderRadius: 8, padding: "8px 16px", fontSize: 14, color: "#475569" }}>
              {result.model_used}
            </div>
            {result.hipaa_compliant && (
              <div style={{ background: "#d1fae5", borderRadius: 8, padding: "8px 16px", fontSize: 14, color: "#065f46" }}>
                🔒 HIPAA Compliant
              </div>
            )}
          </div>

          <div style={{ background: "white", border: "1px solid #e2e8f0", borderRadius: 12, padding: 24, marginBottom: 16 }}>
            <h3 style={{ margin: "0 0 12px", color: "#0f172a" }}>Clinical Response</h3>
            <div style={{ lineHeight: 1.7, color: "#334155", whiteSpace: "pre-wrap" }}>{result.answer}</div>
          </div>

          {result.sources.length > 0 && (
            <div style={{ background: "#f8fafc", borderRadius: 12, padding: 16 }}>
              <h4 style={{ margin: "0 0 8px" }}>Source Documents</h4>
              {result.sources.map((src, i) => (
                <div key={i} style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", borderBottom: "1px solid #e2e8f0", fontSize: 14 }}>
                  <span>📄 {src.source}</span>
                  <span style={{ color: "#059669", fontWeight: 600 }}>Score: {src.score}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
