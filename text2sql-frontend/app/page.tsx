"use client";

import { FormEvent, useState } from "react";

type Answer = {
  sql: string | null;
  columns: string[];
  rows: unknown[][];
  explanation: string;
  off_topic?: boolean;
};

type HistoryItem = {
  id: number;
  question: string;
  answer: Answer;
};

const examples = [
  "How many films are in the database?",
  "Show the five customers with the most rentals.",
  "What is the total payment revenue per category?",
  "List films with a PG rating and rental rate under $2.",
];

const apiUrl = process.env.NEXT_PUBLIC_API_URL;

function DatabaseMark() {
  return (
    <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-[#e0f2e8] text-[#177b5b]">
      <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" className="h-5 w-5">
        <ellipse cx="12" cy="5" rx="7.5" ry="3" stroke="currentColor" strokeWidth="1.8" />
        <path d="M4.5 5v7c0 1.65 3.36 3 7.5 3 .9 0 1.76-.07 2.56-.2M19.5 5v4" stroke="currentColor" strokeWidth="1.8" />
        <path d="M4.5 12v7c0 1.66 3.36 3 7.5 3 1.02 0 1.98-.09 2.85-.25M19.5 12v7M15 15.5h7m-3.5-3.5v7" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      </svg>
    </div>
  );
}

function formatCell(value: unknown): string {
  if (value === null || value === undefined) return "NULL";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export default function Home() {
  const [question, setQuestion] = useState("");
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [copiedId, setCopiedId] = useState<number | null>(null);

  async function askQuestion(value: string) {
    const trimmed = value.trim();
    if (!trimmed || loading) return;

    setQuestion(trimmed);
    setError("");
    setLoading(true);

    try {
      if (!apiUrl) throw new Error("API URL is not configured. Set NEXT_PUBLIC_API_URL in .env.local and restart the frontend.");

      const response = await fetch(`${apiUrl.replace(/\/$/, "")}/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: trimmed }),
        signal: AbortSignal.timeout(25_000),
      });

      const data = await response.json().catch(() => null);
      if (!response.ok) {
        const detail = data?.detail;
        throw new Error(typeof detail === "string" ? detail : `The request failed (${response.status}). Please try again.`);
      }

      const answer = data as Answer;
      setHistory((current) => [{ id: Date.now(), question: trimmed, answer }, ...current]);
      setQuestion("");
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : "Something went wrong. Please try again.";
      setError(cause instanceof DOMException && cause.name === "TimeoutError"
        ? "The request took too long. Please try again in a moment."
        : message.includes("Failed to fetch")
        ? "Could not reach the API. Check that the backend is running at the configured URL."
        : message);
    } finally {
      setLoading(false);
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void askQuestion(question);
  }

  async function copySql(id: number, sql: string) {
    try {
      await navigator.clipboard.writeText(sql);
      setCopiedId(id);
      window.setTimeout(() => setCopiedId((current) => current === id ? null : current), 1600);
    } catch {
      setError("Could not copy the SQL. Select the query and copy it manually.");
    }
  }

  return (
    <main className="min-h-screen px-4 pb-16 pt-5 sm:px-8 sm:pt-8">
      <div className="mx-auto max-w-4xl">
        <header className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <DatabaseMark />
            <div>
              <p className="text-sm font-bold tracking-tight text-[#21352c]">QueryPal</p>
              <p className="text-xs text-[#829087]">Text to SQL assistant</p>
            </div>
          </div>
          <div className="hidden items-center gap-2 rounded-full border border-[#dfe9e1] bg-white/75 px-3 py-1.5 text-xs font-medium text-[#52665b] sm:flex">
            <span className="h-1.5 w-1.5 rounded-full bg-[#36a575]" />
            Pagila · PostgreSQL
          </div>
        </header>

        <section className="mx-auto mt-14 max-w-3xl text-center sm:mt-20">
          <div className="mx-auto mb-5 flex w-fit items-center gap-2 rounded-full border border-[#dce9df] bg-white/75 px-3 py-1.5 text-xs font-semibold text-[#41745a] shadow-sm shadow-[#1c3d2c]/[0.03]">
            <span className="h-1.5 w-1.5 rounded-full bg-[#38a273]" />
            Your database, in plain English
          </div>
          <h1 className="text-4xl font-semibold tracking-[-0.045em] text-[#18251f] sm:text-5xl">
            Ask your database<span className="text-[#25936b]">.</span>
          </h1>
          <p className="mx-auto mt-4 max-w-xl text-sm leading-6 text-[#748179] sm:text-base">
            Ask a question about films, rentals, or customers. Get a clear answer backed by SQL.
          </p>

          <form onSubmit={handleSubmit} className="mt-8 rounded-2xl border border-[#dce5de] bg-white p-2 shadow-[0_16px_50px_-32px_rgba(24,58,39,.3)] transition focus-within:border-[#9fcdb1] focus-within:ring-4 focus-within:ring-[#dcefe2]/70">
            <label htmlFor="question" className="sr-only">Ask a question about the database</label>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
              <input
                id="question"
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                placeholder="e.g. Which categories earn the most revenue?"
                className="min-h-12 min-w-0 flex-1 bg-transparent px-3 text-left text-sm text-[#26332c] outline-none placeholder:text-[#a0aaa3] sm:px-4"
                disabled={loading}
              />
              <button
                type="submit"
                disabled={loading || !question.trim()}
                className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-[#177b5b] px-5 text-sm font-semibold text-white transition hover:bg-[#116348] disabled:cursor-not-allowed disabled:opacity-55"
              >
                {loading ? (
                  <><span className="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white" /> Thinking</>
                ) : (
                  <>Ask <span aria-hidden="true">↗</span></>
                )}
              </button>
            </div>
          </form>

          {error && (
            <div role="alert" className="mt-4 rounded-xl border border-[#f0cfca] bg-[#fff5f3] px-4 py-3 text-left text-sm text-[#a33f35]">
              <span className="mr-2 font-bold">!</span>{error}
            </div>
          )}

          <div className="mt-5 flex flex-wrap items-center justify-center gap-2">
            <span className="mr-1 text-xs text-[#919c94]">Try asking</span>
            {examples.map((example) => (
              <button
                key={example}
                type="button"
                onClick={() => { setQuestion(example); setError(""); }}
                disabled={loading}
                className="rounded-full border border-[#e1e8e2] bg-white/70 px-3 py-1.5 text-xs text-[#66746b] transition hover:border-[#a9ceb6] hover:bg-white hover:text-[#216d50] disabled:opacity-50"
              >
                {example}
              </button>
            ))}
          </div>
        </section>

        <section className="mt-12 space-y-5" aria-label="Answer history" aria-live="polite">
          {history.map((item) => (
            <article key={item.id} className="overflow-hidden rounded-2xl border border-[#e1e8e2] bg-white shadow-[0_12px_36px_-28px_rgba(24,58,39,.3)]">
              <div className="border-b border-[#edf1ed] px-5 py-4 sm:px-6">
                <div className="flex items-start gap-3">
                  <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[#e4f3e9] text-xs font-bold text-[#267552]">Q</div>
                  <div>
                    <p className="text-sm font-medium leading-6 text-[#2b3830]">{item.question}</p>
                    <p className="mt-1 text-[11px] uppercase tracking-[.12em] text-[#a1aaa3]">Your question</p>
                  </div>
                </div>
              </div>

              <div className="px-5 py-5 sm:px-6">
                <div className="flex items-start gap-3">
                  <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[#f0f4f1] text-[#4c6555]">
                    <svg viewBox="0 0 20 20" fill="none" aria-hidden="true" className="h-4 w-4">
                      <path d="M10 2.5v2m0 11v2m7.5-7.5h-2m-11 0h-2m12.8-5.3-1.4 1.4M4.1 15.9l-1.4 1.4m14.6 0-1.4-1.4M4.1 4.1 2.7 2.7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                      <circle cx="10" cy="10" r="3.2" stroke="currentColor" strokeWidth="1.5" />
                    </svg>
                  </div>
                  <div className="min-w-0 flex-1">
                    {item.answer.off_topic ? (
                      <div role="status" className="rounded-xl border border-[#eadfba] bg-[#fbf8ed] px-4 py-3 text-sm leading-6 text-[#756642]">
                        <div className="flex items-start gap-2.5">
                          <span aria-hidden="true" className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[#f1e9cf] text-xs font-semibold text-[#887443]">i</span>
                          <p>{item.answer.explanation}</p>
                        </div>
                      </div>
                    ) : (
                      <>
                        <p className="text-sm leading-6 text-[#5a685f]">{item.answer.explanation}</p>
                        <div className="mt-5 overflow-hidden rounded-xl border border-[#26362f] bg-[#17231e]">
                          <div className="flex items-center justify-between border-b border-white/[.08] px-4 py-2.5">
                            <div className="flex items-center gap-2">
                              <span className="h-2 w-2 rounded-full bg-[#61c795]" />
                              <span className="text-[11px] font-semibold uppercase tracking-[.14em] text-[#bac9bf]">PostgreSQL</span>
                            </div>
                            <button
                              type="button"
                              onClick={() => item.answer.sql && void copySql(item.id, item.answer.sql)}
                              className="rounded-md px-2 py-1 text-xs text-[#b9c9bf] transition hover:bg-white/10 hover:text-white"
                            >
                              {copiedId === item.id ? "Copied" : "Copy SQL"}
                            </button>
                          </div>
                          <pre className="max-h-72 overflow-auto p-4 text-left text-xs leading-6 text-[#d9e8df] sm:text-[13px]"><code>{item.answer.sql}</code></pre>
                        </div>

                        <div className="mt-5">
                          <div className="mb-2 flex items-center justify-between">
                            <h2 className="text-xs font-semibold uppercase tracking-[.12em] text-[#819087]">Results</h2>
                            <span className="text-xs text-[#9aa59d]">{item.answer.rows.length} {item.answer.rows.length === 1 ? "row" : "rows"}</span>
                          </div>
                          {item.answer.columns.length === 0 ? (
                            <p className="rounded-xl border border-dashed border-[#dce5de] px-4 py-6 text-center text-sm text-[#8a968e]">No columns were returned.</p>
                          ) : item.answer.rows.length === 0 ? (
                            <p className="rounded-xl border border-dashed border-[#dce5de] px-4 py-6 text-center text-sm text-[#8a968e]">The query ran successfully but returned no rows.</p>
                          ) : (
                            <div className="max-h-80 overflow-auto rounded-xl border border-[#e4eae5]">
                              <table className="min-w-full border-collapse text-left text-xs">
                                <thead className="sticky top-0 bg-[#f5f8f5] text-[#637168]">
                                  <tr>{item.answer.columns.map((column, index) => <th key={`${column}-${index}`} className="whitespace-nowrap border-b border-[#e4eae5] px-4 py-3 font-semibold">{column}</th>)}</tr>
                                </thead>
                                <tbody className="divide-y divide-[#edf1ed] text-[#45544a]">
                                  {item.answer.rows.map((row, rowIndex) => (
                                    <tr key={rowIndex} className="odd:bg-white even:bg-[#fbfcfb]">
                                      {row.map((value, columnIndex) => (
                                        <td key={columnIndex} className={`max-w-[24rem] px-4 py-3 align-top ${value == null ? "italic text-[#a5aea8]" : ""}`}>
                                          <span className="block max-h-20 overflow-auto whitespace-pre-wrap break-words">{formatCell(value)}</span>
                                        </td>
                                      ))}
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          )}
                        </div>
                      </>
                    )}
                  </div>
                </div>
              </div>
            </article>
          ))}

          {history.length === 0 && !loading && (
            <div className="mx-auto mt-10 max-w-md py-7 text-center">
              <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl border border-[#e1e9e2] bg-white text-[#88a393] shadow-sm">
                <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" className="h-5 w-5">
                  <path d="M7 4.5h10a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2v-11a2 2 0 0 1 2-2Z" stroke="currentColor" strokeWidth="1.5" />
                  <path d="M8.5 9h7m-7 3h7m-7 3h4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                </svg>
              </div>
              <p className="mt-4 text-sm font-medium text-[#536158]">Your answers will show up here</p>
              <p className="mt-1 text-xs leading-5 text-[#919b94]">Start with one of the examples above, or ask your own question.</p>
            </div>
          )}
        </section>

        <footer className="mt-14 text-center text-[11px] text-[#a0aaa3]">
          QueryPal · Read-only queries on the Pagila database
        </footer>
      </div>
    </main>
  );
}
