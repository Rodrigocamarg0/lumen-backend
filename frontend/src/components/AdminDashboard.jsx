import { useCallback, useEffect, useMemo, useState } from "react";
import { useAuth } from "../auth/useAuth.js";
import {
  fetchAdminPersonas,
  fetchAdminStats,
  fetchAdminTraces,
  updateAdminPersona,
} from "../lib/api.js";

const tabs = [
  { id: "overview", label: "Overview" },
  { id: "traces", label: "Traces" },
  { id: "prompts", label: "Prompts" },
];

function formatNumber(value, suffix = "") {
  if (value === null || value === undefined) return "—";
  return `${Intl.NumberFormat("en-US", { maximumFractionDigits: 1 }).format(value)}${suffix}`;
}

function formatTime(ts) {
  if (!ts) return "—";
  return new Date(ts * 1000).toLocaleString();
}

function Kpi({ label, value, detail }) {
  return (
    <div className="min-w-0 border-b border-gray-200 dark:border-gray-800 pb-4">
      <div className="text-xs uppercase tracking-wide text-gray-500 dark:text-gray-400">
        {label}
      </div>
      <div className="mt-2 text-2xl font-semibold text-gray-950 dark:text-gray-50">
        {value}
      </div>
      {detail && (
        <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
          {detail}
        </div>
      )}
    </div>
  );
}

function MiniBars({ series, metric }) {
  const values = series.map((point) => Number(point[metric] ?? 0));
  const max = Math.max(...values, 1);
  return (
    <div className="flex h-32 items-end gap-1 border-b border-gray-200 dark:border-gray-800">
      {series.map((point) => (
        <div
          key={`${metric}-${point.date}`}
          title={`${point.date}: ${formatNumber(point[metric])}`}
          className="flex flex-1 items-end"
        >
          <div
            className="w-full bg-orange-500/80 dark:bg-orange-400/80 transition-all"
            style={{
              height: `${Math.max(6, (Number(point[metric] ?? 0) / max) * 100)}%`,
            }}
          />
        </div>
      ))}
    </div>
  );
}

function Overview({ stats }) {
  if (!stats) return null;
  return (
    <div className="space-y-8">
      <div className="grid grid-cols-2 gap-5 lg:grid-cols-4">
        <Kpi
          label="DAU"
          value={formatNumber(stats.daily_active_users)}
          detail="Last 24 hours"
        />
        <Kpi
          label="WAU"
          value={formatNumber(stats.weekly_active_users)}
          detail="Last 7 days"
        />
        <Kpi
          label="MAU"
          value={formatNumber(stats.monthly_active_users)}
          detail="Last 30 days"
        />
        <Kpi
          label="Concurrent"
          value={formatNumber(stats.concurrent_sessions)}
          detail="Active in 15 minutes"
        />
        <Kpi
          label="Users"
          value={formatNumber(stats.total_users)}
          detail="Registered"
        />
        <Kpi
          label="Sessions"
          value={formatNumber(stats.total_sessions)}
          detail="All time"
        />
        <Kpi
          label="Interactions"
          value={formatNumber(stats.total_interactions)}
          detail="LLM runs"
        />
        <Kpi
          label="LGPD accepts"
          value={formatNumber(stats.terms_acceptances)}
          detail="Audit rows"
        />
      </div>

      <div className="grid gap-8 lg:grid-cols-3">
        <section className="space-y-3">
          <div>
            <h2 className="text-sm font-semibold text-gray-950 dark:text-gray-50">
              Requests per day
            </h2>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              Last 14 days
            </p>
          </div>
          <MiniBars series={stats.series} metric="runs" />
        </section>
        <section className="space-y-3">
          <div>
            <h2 className="text-sm font-semibold text-gray-950 dark:text-gray-50">
              Tokens/sec
            </h2>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              Daily average
            </p>
          </div>
          <MiniBars series={stats.series} metric="avg_tokens_per_second" />
        </section>
        <section className="space-y-3">
          <div>
            <h2 className="text-sm font-semibold text-gray-950 dark:text-gray-50">
              Generation latency
            </h2>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              Daily average in ms
            </p>
          </div>
          <MiniBars series={stats.series} metric="avg_generation_latency_ms" />
        </section>
      </div>
    </div>
  );
}

function Traces({
  traces,
  filters,
  setFilters,
  selectedTrace,
  setSelectedTrace,
  reload,
}) {
  return (
    <div className="grid min-h-0 gap-6 xl:grid-cols-[minmax(0,1fr)_420px]">
      <div className="min-w-0 space-y-4">
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-xs text-gray-500 dark:text-gray-400">
            Persona
            <input
              className="mt-1 block w-36 border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-700 dark:bg-gray-900"
              value={filters.persona}
              onChange={(event) =>
                setFilters((prev) => ({ ...prev, persona: event.target.value }))
              }
            />
          </label>
          <label className="text-xs text-gray-500 dark:text-gray-400">
            Status
            <select
              className="mt-1 block w-36 border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-700 dark:bg-gray-900"
              value={filters.status}
              onChange={(event) =>
                setFilters((prev) => ({ ...prev, status: event.target.value }))
              }
            >
              <option value="">Any</option>
              <option value="completed">Completed</option>
              <option value="failed">Failed</option>
            </select>
          </label>
          <label className="text-xs text-gray-500 dark:text-gray-400">
            Min latency
            <input
              type="number"
              min="0"
              className="mt-1 block w-32 border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-700 dark:bg-gray-900"
              value={filters.min_latency_ms}
              onChange={(event) =>
                setFilters((prev) => ({
                  ...prev,
                  min_latency_ms: event.target.value,
                }))
              }
            />
          </label>
          <button
            type="button"
            onClick={reload}
            className="border border-gray-900 bg-gray-900 px-4 py-2 text-sm font-medium text-white dark:border-gray-100 dark:bg-gray-100 dark:text-gray-950"
          >
            Apply
          </button>
        </div>

        <div className="overflow-x-auto border-y border-gray-200 dark:border-gray-800">
          <table className="w-full min-w-[760px] text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-gray-500 dark:text-gray-400">
              <tr>
                <th className="py-3 pr-4">Created</th>
                <th className="py-3 pr-4">Persona</th>
                <th className="py-3 pr-4">Model</th>
                <th className="py-3 pr-4">Status</th>
                <th className="py-3 pr-4">Tokens</th>
                <th className="py-3 pr-4">TPS</th>
                <th className="py-3 pr-4">Latency</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 dark:divide-gray-800">
              {(traces?.items ?? []).map((trace) => (
                <tr
                  key={trace.id}
                  onClick={() => setSelectedTrace(trace)}
                  className="cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800/60"
                >
                  <td className="py-3 pr-4 text-gray-600 dark:text-gray-300">
                    {formatTime(trace.created_at)}
                  </td>
                  <td className="py-3 pr-4">{trace.persona_id}</td>
                  <td className="py-3 pr-4 text-gray-600 dark:text-gray-300">
                    {trace.model_id}
                  </td>
                  <td className="py-3 pr-4">{trace.status}</td>
                  <td className="py-3 pr-4">
                    {formatNumber(trace.tokens_generated)}
                  </td>
                  <td className="py-3 pr-4">
                    {formatNumber(trace.tokens_per_second)}
                  </td>
                  <td className="py-3 pr-4">
                    {formatNumber(trace.generation_latency_ms, " ms")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <aside className="min-h-[360px] border-l border-gray-200 pl-6 dark:border-gray-800">
        {selectedTrace ? (
          <div className="space-y-5">
            <div>
              <h2 className="text-sm font-semibold text-gray-950 dark:text-gray-50">
                Trace detail
              </h2>
              <p className="mt-1 break-all text-xs text-gray-500 dark:text-gray-400">
                {selectedTrace.id}
              </p>
            </div>
            <div className="grid grid-cols-2 gap-3 text-xs">
              <Kpi
                label="RAG"
                value={formatNumber(selectedTrace.rag_latency_ms, " ms")}
              />
              <Kpi
                label="Generation"
                value={formatNumber(selectedTrace.generation_latency_ms, " ms")}
              />
            </div>
            {selectedTrace.error_detail && (
              <pre className="whitespace-pre-wrap bg-red-50 p-3 text-xs text-red-900 dark:bg-red-950/30 dark:text-red-200">
                {selectedTrace.error_detail}
              </pre>
            )}
            {selectedTrace.messages.map((message, index) => (
              <section key={`${message.role}-${index}`} className="space-y-2">
                <h3 className="text-xs uppercase tracking-wide text-gray-500 dark:text-gray-400">
                  {message.role}
                </h3>
                <p className="max-h-48 overflow-y-auto whitespace-pre-wrap text-sm leading-6">
                  {message.content}
                </p>
                {message.citations && (
                  <pre className="max-h-36 overflow-auto bg-gray-50 p-3 text-xs dark:bg-gray-900">
                    {JSON.stringify(message.citations, null, 2)}
                  </pre>
                )}
              </section>
            ))}
          </div>
        ) : (
          <div className="flex h-full items-center text-sm text-gray-500 dark:text-gray-400">
            Select a trace to inspect the prompt, response, citations, and
            latency.
          </div>
        )}
      </aside>
    </div>
  );
}

function Prompts({
  personas,
  selectedPersonaId,
  setSelectedPersonaId,
  savePersona,
}) {
  const selected =
    personas.find((persona) => persona.persona_id === selectedPersonaId) ??
    personas[0];
  const [systemPrompt, setSystemPrompt] = useState("");
  const [fewShotJson, setFewShotJson] = useState("[]");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!selected) return;
    setSystemPrompt(selected.system_prompt);
    setFewShotJson(JSON.stringify(selected.few_shot_examples ?? [], null, 2));
    setError("");
  }, [selected]);

  async function handleSave() {
    try {
      const fewShot = JSON.parse(fewShotJson);
      if (!Array.isArray(fewShot)) {
        throw new Error("Few-shot examples must be a JSON array.");
      }
      await savePersona(selected.persona_id, {
        system_prompt: systemPrompt,
        few_shot_examples: fewShot,
      });
      setError("");
    } catch (err) {
      setError(err.message);
    }
  }

  if (!selected) return null;
  return (
    <div className="grid gap-6 xl:grid-cols-[220px_minmax(0,1fr)]">
      <nav className="space-y-1 border-r border-gray-200 pr-4 dark:border-gray-800">
        {personas.map((persona) => (
          <button
            key={persona.persona_id}
            type="button"
            onClick={() => setSelectedPersonaId(persona.persona_id)}
            className={`block w-full px-3 py-2 text-left text-sm ${
              persona.persona_id === selected.persona_id
                ? "bg-gray-950 text-white dark:bg-gray-100 dark:text-gray-950"
                : "text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800"
            }`}
          >
            {persona.persona_id}
          </button>
        ))}
      </nav>
      <div className="min-w-0 space-y-4">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h2 className="text-sm font-semibold text-gray-950 dark:text-gray-50">
              {selected.persona_id}
            </h2>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              Last update: {formatTime(selected.updated_at)}
            </p>
          </div>
          <button
            type="button"
            onClick={handleSave}
            className="border border-orange-600 bg-orange-600 px-4 py-2 text-sm font-medium text-white"
          >
            Save
          </button>
        </div>
        {error && (
          <div className="text-sm text-red-600 dark:text-red-300">{error}</div>
        )}
        <label className="block text-xs uppercase tracking-wide text-gray-500 dark:text-gray-400">
          System prompt
          <textarea
            className="mt-2 h-80 w-full resize-y border border-gray-300 bg-white p-3 font-mono text-sm leading-6 dark:border-gray-700 dark:bg-gray-900"
            value={systemPrompt}
            onChange={(event) => setSystemPrompt(event.target.value)}
          />
        </label>
        <label className="block text-xs uppercase tracking-wide text-gray-500 dark:text-gray-400">
          Few-shot examples JSON
          <textarea
            className="mt-2 h-72 w-full resize-y border border-gray-300 bg-white p-3 font-mono text-sm leading-6 dark:border-gray-700 dark:bg-gray-900"
            value={fewShotJson}
            onChange={(event) => setFewShotJson(event.target.value)}
          />
        </label>
      </div>
    </div>
  );
}

export default function AdminDashboard() {
  const { accessToken, user, signOut } = useAuth();
  const isAdmin = user?.app_metadata?.role === "admin";
  const [activeTab, setActiveTab] = useState("overview");
  const [stats, setStats] = useState(null);
  const [traces, setTraces] = useState(null);
  const [personas, setPersonas] = useState([]);
  const [selectedTrace, setSelectedTrace] = useState(null);
  const [selectedPersonaId, setSelectedPersonaId] = useState("");
  const [filters, setFilters] = useState({
    limit: 50,
    offset: 0,
    persona: "",
    status: "",
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadAll = useCallback(async () => {
    if (!accessToken || !isAdmin) return;
    setLoading(true);
    setError("");
    try {
      const [nextStats, nextTraces, nextPersonas] = await Promise.all([
        fetchAdminStats(accessToken),
        fetchAdminTraces(filters, accessToken),
        fetchAdminPersonas(accessToken),
      ]);
      setStats(nextStats);
      setTraces(nextTraces);
      setPersonas(nextPersonas);
      setSelectedPersonaId(
        (current) => current || nextPersonas[0]?.persona_id || "",
      );
      setSelectedTrace((current) => current ?? nextTraces.items?.[0] ?? null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [accessToken, filters, isAdmin]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const reloadTraces = useCallback(async () => {
    setError("");
    try {
      const nextTraces = await fetchAdminTraces(filters, accessToken);
      setTraces(nextTraces);
      setSelectedTrace(nextTraces.items?.[0] ?? null);
    } catch (err) {
      setError(err.message);
    }
  }, [accessToken, filters]);

  const savePersona = useCallback(
    async (personaId, payload) => {
      const updated = await updateAdminPersona(personaId, payload, accessToken);
      setPersonas((current) =>
        current.map((persona) =>
          persona.persona_id === personaId ? updated : persona,
        ),
      );
    },
    [accessToken],
  );

  const content = useMemo(() => {
    if (activeTab === "overview") return <Overview stats={stats} />;
    if (activeTab === "traces") {
      return (
        <Traces
          traces={traces}
          filters={filters}
          setFilters={setFilters}
          selectedTrace={selectedTrace}
          setSelectedTrace={setSelectedTrace}
          reload={reloadTraces}
        />
      );
    }
    return (
      <Prompts
        personas={personas}
        selectedPersonaId={selectedPersonaId}
        setSelectedPersonaId={setSelectedPersonaId}
        savePersona={savePersona}
      />
    );
  }, [
    activeTab,
    filters,
    personas,
    reloadTraces,
    savePersona,
    selectedPersonaId,
    selectedTrace,
    stats,
    traces,
  ]);

  if (!isAdmin) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-white p-6 text-gray-950 dark:bg-gray-950 dark:text-gray-50">
        <div className="max-w-md space-y-3">
          <h1 className="text-xl font-semibold">Admin access required</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Your Supabase user must have <code>app_metadata.role</code> set to
            admin.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen bg-white text-gray-950 dark:bg-gray-950 dark:text-gray-50">
      <aside className="hidden w-64 shrink-0 border-r border-gray-200 px-5 py-6 dark:border-gray-800 lg:block">
        <div>
          <div className="text-lg font-semibold">Lumen Admin</div>
          <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
            {user.email}
          </div>
        </div>
        <nav className="mt-8 space-y-1">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveTab(tab.id)}
              className={`block w-full px-3 py-2 text-left text-sm ${
                activeTab === tab.id
                  ? "bg-gray-950 text-white dark:bg-gray-100 dark:text-gray-950"
                  : "text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </nav>
        <button
          type="button"
          onClick={signOut}
          className="mt-8 text-sm text-gray-500 hover:text-gray-950 dark:text-gray-400 dark:hover:text-gray-50"
        >
          Sign out
        </button>
      </aside>
      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-gray-200 px-5 py-4 dark:border-gray-800">
          <div>
            <h1 className="text-xl font-semibold">Admin Dashboard</h1>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Usage, trace inspection, and persona prompt configuration.
            </p>
          </div>
          <div className="flex gap-2 lg:hidden">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                type="button"
                onClick={() => setActiveTab(tab.id)}
                className={`px-3 py-2 text-sm ${
                  activeTab === tab.id
                    ? "bg-gray-950 text-white dark:bg-gray-100 dark:text-gray-950"
                    : "text-gray-600 dark:text-gray-300"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-6">
          {error && (
            <div className="mb-5 border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-900 dark:border-red-900 dark:bg-red-950/30 dark:text-red-200">
              {error}
            </div>
          )}
          {loading ? (
            <div className="text-sm text-gray-500 dark:text-gray-400">
              Loading admin data...
            </div>
          ) : (
            content
          )}
        </div>
      </main>
    </div>
  );
}
