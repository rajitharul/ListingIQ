"use client";

import { useCallback, useEffect, useState } from "react";
import Header from "@/components/Header";
import type { AdminAccount, CurrentUser } from "@/types";

const LIMIT_FIELDS = [
  { key: "rpm_limit", label: "Requests / min" },
  { key: "max_concurrent", label: "Concurrent runs" },
  { key: "daily_token_limit", label: "Tokens / day" },
] as const;

export default function AdminPage() {
  const [me, setMe] = useState<CurrentUser | null>(null);
  const [accounts, setAccounts] = useState<AdminAccount[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setError(null);
    try {
      const meRes = await fetch("/api/auth/me");
      if (!meRes.ok) throw new Error("Your session has expired. Please sign in again.");
      const meBody: CurrentUser = await meRes.json();
      setMe(meBody);

      const res = await fetch("/api/admin/accounts");
      if (res.status === 403) throw new Error("Administrator access required.");
      if (!res.ok) throw new Error((await res.json()).detail ?? "Could not load accounts.");
      setAccounts(await res.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const flash = (msg: string) => {
    setNotice(msg);
    setTimeout(() => setNotice(null), 6000);
  };

  const patch = async (id: string, body: Record<string, unknown>, ok: string) => {
    setError(null);
    const res = await fetch(`/api/admin/accounts/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      setError(data.detail ?? "Update failed.");
      return;
    }
    flash(ok);
    load();
  };

  if (loading) {
    return (
      <div className="min-h-screen flex flex-col">
        <Header />
        <main className="flex-1 max-w-6xl mx-auto w-full px-6 py-10">
          <p className="text-sm text-[var(--text-muted)]">Loading accounts…</p>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col">
      <Header />
      <main className="flex-1 max-w-6xl mx-auto w-full px-6 py-8 space-y-8">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight">Accounts</h1>
          <p className="text-sm text-[var(--text-muted)] mt-1">
            Create accounts and set how much each one may spend.
          </p>
        </div>

        {error && (
          <div
            role="alert"
            className="glass-card p-4 border-[var(--score-low)]/30 bg-[var(--score-low)]/5"
          >
            <p className="text-sm text-[var(--score-low)]">{error}</p>
          </div>
        )}
        {notice && (
          <div className="glass-card p-4 border-emerald-600/30 bg-emerald-600/5">
            <p className="text-sm text-emerald-700">{notice}</p>
          </div>
        )}

        {me && !me.role.includes("admin") ? null : (
          <CreateAccountForm onCreated={(msg) => { flash(msg); load(); }} />
        )}

        <section className="glass-card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wide text-[var(--text-muted)] border-b border-[var(--card-border)]">
                  <th className="px-4 py-3">Account</th>
                  <th className="px-4 py-3">Role</th>
                  <th className="px-4 py-3 text-right">Req/min</th>
                  <th className="px-4 py-3 text-right">Concurrent</th>
                  <th className="px-4 py-3 text-right">Tokens/day</th>
                  <th className="px-4 py-3 text-right">Used today</th>
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody>
                {accounts.map((a) => (
                  <AccountRow
                    key={a.account_id}
                    account={a}
                    isSelf={me?.account_id === a.account_id}
                    onPatch={patch}
                    onPasswordSet={flash}
                  />
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <p className="text-xs text-[var(--text-muted)]">
          Limits apply per account. A disabled account cannot sign in, and its API
          keys stop working immediately.
        </p>
      </main>
    </div>
  );
}

function AccountRow({
  account,
  isSelf,
  onPatch,
  onPasswordSet,
}: {
  account: AdminAccount;
  isSelf: boolean;
  onPatch: (id: string, body: Record<string, unknown>, ok: string) => void;
  onPasswordSet: (msg: string) => void;
}) {
  const [draft, setDraft] = useState<Record<string, number>>({
    rpm_limit: account.rpm_limit,
    max_concurrent: account.max_concurrent,
    daily_token_limit: account.daily_token_limit,
  });
  const dirty = LIMIT_FIELDS.some(
    (f) => draft[f.key] !== (account[f.key] as number),
  );
  const pct = account.daily_token_limit
    ? Math.min(100, (account.usage_today.tokens / account.daily_token_limit) * 100)
    : 0;

  return (
    <tr className="border-b border-[var(--card-border)] last:border-0">
      <td className="px-4 py-3">
        <div className="font-medium">{account.email}</div>
        <div className="text-xs text-[var(--text-muted)] font-mono">
          {account.account_id}
        </div>
      </td>
      <td className="px-4 py-3">
        <span
          className={`text-xs px-2 py-0.5 rounded-full ${
            account.role === "admin"
              ? "bg-emerald-600/10 text-emerald-700"
              : "bg-[var(--card-border)]/40 text-[var(--text-muted)]"
          }`}
        >
          {account.role}
        </span>
        {!account.active && (
          <span className="ml-2 text-xs px-2 py-0.5 rounded-full bg-[var(--score-low)]/10 text-[var(--score-low)]">
            disabled
          </span>
        )}
      </td>

      {LIMIT_FIELDS.map((f) => (
        <td key={f.key} className="px-4 py-3 text-right">
          <input
            type="number"
            min={0}
            aria-label={`${f.label} for ${account.email}`}
            value={draft[f.key]}
            onChange={(e) =>
              setDraft({ ...draft, [f.key]: Number(e.target.value) })
            }
            className="w-28 px-2 py-1 text-right rounded border border-[var(--card-border)] bg-[var(--background)] text-sm"
          />
        </td>
      ))}

      <td className="px-4 py-3 text-right">
        <div className="text-xs">
          {account.usage_today.tokens.toLocaleString()}
        </div>
        <div className="h-1 w-24 ml-auto mt-1 rounded bg-[var(--card-border)]/50 overflow-hidden">
          <div
            className="h-full bg-emerald-600"
            style={{ width: `${pct}%` }}
          />
        </div>
        <div className="text-[10px] text-[var(--text-muted)] mt-0.5">
          {account.usage_today.runs} run{account.usage_today.runs === 1 ? "" : "s"}
        </div>
      </td>

      <td className="px-4 py-3">
        <div className="flex gap-2 justify-end flex-wrap">
          {dirty && (
            <button
              onClick={() =>
                onPatch(account.account_id, draft, `Limits updated for ${account.email}.`)
              }
              className="text-xs px-2.5 py-1 rounded bg-emerald-600 text-white hover:bg-emerald-700"
            >
              Save
            </button>
          )}
          <button
            onClick={() =>
              onPatch(
                account.account_id,
                { role: account.role === "admin" ? "member" : "admin" },
                `${account.email} is now ${account.role === "admin" ? "a member" : "an admin"}.`,
              )
            }
            className="text-xs px-2.5 py-1 rounded border border-[var(--card-border)] hover:bg-[var(--card-border)]/20"
          >
            {account.role === "admin" ? "Demote" : "Make admin"}
          </button>
          <button
            onClick={() =>
              onPatch(
                account.account_id,
                { active: !account.active },
                `${account.email} ${account.active ? "disabled" : "re-enabled"}.`,
              )
            }
            disabled={isSelf}
            title={isSelf ? "You cannot disable your own account" : undefined}
            className="text-xs px-2.5 py-1 rounded border border-[var(--card-border)] hover:bg-[var(--card-border)]/20 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {account.active ? "Disable" : "Enable"}
          </button>
          <ResetPassword account={account} onDone={onPasswordSet} />
        </div>
      </td>
    </tr>
  );
}

function ResetPassword({
  account,
  onDone,
}: {
  account: AdminAccount;
  onDone: (msg: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [pw, setPw] = useState("");
  const [err, setErr] = useState<string | null>(null);

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="text-xs px-2.5 py-1 rounded border border-[var(--card-border)] hover:bg-[var(--card-border)]/20"
      >
        Set password
      </button>
    );
  }

  const submit = async () => {
    setErr(null);
    const res = await fetch(`/api/admin/accounts/${account.account_id}/password`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: pw }),
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      setErr(body.detail ?? "Could not set password.");
      return;
    }
    setOpen(false);
    setPw("");
    onDone(`Password set for ${account.email}. Their sessions were signed out.`);
  };

  return (
    <span className="inline-flex items-center gap-1">
      <input
        type="password"
        value={pw}
        autoFocus
        placeholder="New password"
        aria-label={`New password for ${account.email}`}
        onChange={(e) => setPw(e.target.value)}
        className="w-36 px-2 py-1 rounded border border-[var(--card-border)] bg-[var(--background)] text-xs"
      />
      <button
        onClick={submit}
        className="text-xs px-2 py-1 rounded bg-emerald-600 text-white hover:bg-emerald-700"
      >
        Set
      </button>
      <button
        onClick={() => { setOpen(false); setErr(null); }}
        className="text-xs px-2 py-1 rounded border border-[var(--card-border)]"
      >
        Cancel
      </button>
      {err && <span className="text-xs text-[var(--score-low)]">{err}</span>}
    </span>
  );
}

function CreateAccountForm({ onCreated }: { onCreated: (msg: string) => void }) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({
    email: "",
    password: "",
    role: "member",
    rpm_limit: 10,
    max_concurrent: 2,
    daily_token_limit: 2000000,
  });
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="px-4 py-2 rounded-lg bg-emerald-600 text-white text-sm font-semibold hover:bg-emerald-700"
      >
        New account
      </button>
    );
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    const res = await fetch("/api/admin/accounts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(form),
    });
    const body = await res.json().catch(() => ({}));
    setBusy(false);
    if (!res.ok) {
      setErr(body.detail ?? "Could not create the account.");
      return;
    }
    setOpen(false);
    setForm({ ...form, email: "", password: "" });
    onCreated(`Created ${body.email}.`);
  };

  return (
    <form onSubmit={submit} className="glass-card p-6 space-y-4">
      <h2 className="font-semibold">New account</h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <label className="text-sm">
          Email
          <input
            type="email"
            required
            value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
            className="mt-1 w-full px-3 py-2 rounded-lg border border-[var(--card-border)] bg-[var(--background)] text-sm"
          />
        </label>
        <label className="text-sm">
          Password <span className="text-[var(--text-muted)]">(min 10 characters)</span>
          <input
            type="password"
            required
            minLength={10}
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
            className="mt-1 w-full px-3 py-2 rounded-lg border border-[var(--card-border)] bg-[var(--background)] text-sm"
          />
        </label>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <label className="text-sm">
          Role
          <select
            value={form.role}
            onChange={(e) => setForm({ ...form, role: e.target.value })}
            className="mt-1 w-full px-3 py-2 rounded-lg border border-[var(--card-border)] bg-[var(--background)] text-sm"
          >
            <option value="member">member</option>
            <option value="admin">admin</option>
          </select>
        </label>
        {LIMIT_FIELDS.map((f) => (
          <label key={f.key} className="text-sm">
            {f.label}
            <input
              type="number"
              min={0}
              value={form[f.key]}
              onChange={(e) =>
                setForm({ ...form, [f.key]: Number(e.target.value) })
              }
              className="mt-1 w-full px-3 py-2 rounded-lg border border-[var(--card-border)] bg-[var(--background)] text-sm"
            />
          </label>
        ))}
      </div>

      {err && <p className="text-sm text-[var(--score-low)]">{err}</p>}

      <div className="flex gap-2">
        <button
          type="submit"
          disabled={busy}
          className="px-4 py-2 rounded-lg bg-emerald-600 text-white text-sm font-semibold hover:bg-emerald-700 disabled:opacity-60"
        >
          {busy ? "Creating…" : "Create account"}
        </button>
        <button
          type="button"
          onClick={() => { setOpen(false); setErr(null); }}
          className="px-4 py-2 rounded-lg border border-[var(--card-border)] text-sm"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}
