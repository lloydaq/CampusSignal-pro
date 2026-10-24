import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Users } from "lucide-react";
import { useId, useState, type FormEvent } from "react";

import { Callout } from "@/components/Callout";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { DataTable, type Column } from "@/components/DataTable";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { useMe } from "@/features/auth/session";
import { KIND_LABEL, roleLabel } from "@/features/campus/labels";
import { usePageTitle } from "@/lib/usePageTitle";

import {
  fetchDepartments,
  fetchMembers,
  grantRole,
  revokeRole,
  updateMember,
  type Department,
  type Grant,
  type Member,
  type MemberFilters,
  type RoleName,
} from "./api";
import { manageKeys } from "./keys";
import { errorText, KIND_OPTIONS, STATUS_LABEL } from "./labels";
import { ListLoading, LoadMore } from "./list";
import { useCursorList } from "./useCursorList";


/** The member directory (PRD §11, §17.12): filters, then a table; college admins manage rows. */
export function MembersTab() {
  usePageTitle("Members · Manage");
  const canManage = useMe().capabilities.includes("manage_college");
  const [filters, setFilters] = useState<MemberFilters>({ query: "", kind: "", status: "ACTIVE" });
  const [search, setSearch] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const { query, items } = useCursorList([...manageKeys.members, filters], (cursor, signal) => fetchMembers(filters, cursor, signal));
  const searchId = useId();
  const kindId = useId();
  const statusId = useId();

  const onSearch = (event: FormEvent) => {
    event.preventDefault();
    setFilters((current) => ({ ...current, query: search.trim() }));
  };

  const columns: Column<Member>[] = [
    {
      header: "Name",
      cell: (m) => (
        <div className="space-y-0.5">
          <p className="font-medium">{m.display_name}</p>
          {m.email && <p className="break-all text-muted">{m.email}</p>}
          {m.roll_number && <p className="font-mono text-muted">{m.roll_number}</p>}
        </div>
      ),
    },
    { header: "Kind", cell: (m) => KIND_LABEL[m.kind] },
    { header: "Department", cell: (m) => m.department?.code ?? <span className="text-muted">Not set</span> },
    { header: "Roles", cell: (m) => (m.roles.length ? m.roles.map(roleLabel).join(", ") : <span className="text-muted">None</span>) },
    { header: "Status", cell: (m) => STATUS_LABEL[m.status] },
  ];
  if (canManage) {
    columns.push({
      header: "Actions",
      cell: (m) => (
        <Button size="sm" variant="ghost" className="-ml-3 md:-my-1.5 md:ml-0" aria-expanded={open === m.id} aria-label={`${open === m.id ? "Close" : "Manage"} ${m.display_name}`} onClick={() => setOpen(open === m.id ? null : m.id)}>
          {open === m.id ? "Close" : "Manage"}
        </Button>
      ),
    });
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <form role="search" onSubmit={onSearch} className="flex min-w-60 flex-1 items-end gap-2">
          <div className="flex-1 space-y-1.5">
            <label htmlFor={searchId} className="block text-sm font-medium">
              Search
            </label>
            <Input id={searchId} type="search" placeholder="Name or email" value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
          <Button type="submit" variant="secondary">
            Search
          </Button>
        </form>
        <div className="space-y-1.5">
          <label htmlFor={kindId} className="block text-sm font-medium">
            Kind
          </label>
          <Select id={kindId} value={filters.kind} onChange={(e) => setFilters((f) => ({ ...f, kind: e.target.value as MemberFilters["kind"] }))}>
            <option value="">All</option>
            {KIND_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
        </div>
        <div className="space-y-1.5">
          <label htmlFor={statusId} className="block text-sm font-medium">
            Status
          </label>
          <Select id={statusId} value={filters.status} onChange={(e) => setFilters((f) => ({ ...f, status: e.target.value as MemberFilters["status"] }))}>
            <option value="">All</option>
            {(Object.keys(STATUS_LABEL) as Member["status"][]).map((s) => (
              <option key={s} value={s}>
                {STATUS_LABEL[s]}
              </option>
            ))}
          </Select>
        </div>
      </div>

      {query.isPending ? (
        <ListLoading label="Loading members" />
      ) : query.isError ? (
        <ErrorState title="Couldn't load the members." error={query.error} onRetry={() => void query.refetch()} retrying={query.isFetching} />
      ) : items.length === 0 ? (
        <EmptyState Icon={Users} title="No members match these filters." />
      ) : (
        <>
          <DataTable
            caption="Members"
            columns={columns}
            rows={items}
            rowKey={(m) => m.id}
            detail={(m) => (canManage && open === m.id ? <MemberPanel member={m} /> : null)}
          />
          <LoadMore shown={items.length} hasMore={query.hasNextPage} loading={query.isFetchingNextPage} onLoad={() => void query.fetchNextPage()} />
        </>
      )}
    </div>
  );
}

type StatusChange = "SUSPENDED" | "ENDED" | "ACTIVE";

const STATUS_CONFIRM: Record<StatusChange, { title: string; description: string; confirm: string; pending: string; reason: boolean }> = {
  SUSPENDED: {
    title: "Suspend this membership?",
    description: "They're signed out of the college and can't open it until you reactivate the membership.",
    confirm: "Suspend",
    pending: "Suspending…",
    reason: true,
  },
  ENDED: {
    title: "End this membership?",
    description: "This can't be undone. They lose access to the college and their roles; they'd have to join again.",
    confirm: "End membership",
    pending: "Ending…",
    reason: true,
  },
  ACTIVE: {
    title: "Reactivate this membership?",
    description: "They can open the college again with the roles they had.",
    confirm: "Reactivate",
    pending: "Reactivating…",
    reason: false,
  },
};

function useMemberChanged() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: manageKeys.members });
}

function MemberPanel({ member }: { member: Member }) {
  const [change, setChange] = useState<StatusChange | null>(null);
  const changed = useMemberChanged();
  const status = useMutation({
    mutationFn: ({ to, reason }: { to: StatusChange; reason: string }) => updateMember(member.id, { status: to, ...(reason ? { reason } : {}) }),
    onSuccess: async () => {
      setChange(null);
      await changed();
    },
  });
  const departments = useQuery({ queryKey: [...manageKeys.departments, false], queryFn: ({ signal }) => fetchDepartments(false, signal), enabled: member.status !== "ENDED" });

  if (member.status === "ENDED") return <p className="text-sm text-muted">This membership has ended. Nothing more can be changed.</p>;
  const changes: StatusChange[] = member.status === "ACTIVE" ? ["SUSPENDED", "ENDED"] : ["ACTIVE", "ENDED"];
  const confirm = change ? STATUS_CONFIRM[change] : null;

  return (
    <div className="space-y-6">
      <section aria-label="Membership status" className="space-y-2">
        <h3 className="text-sm font-semibold">Membership</h3>
        <div className="flex flex-wrap gap-3">
          {changes.map((to) => (
            <Button key={to} size="sm" variant={to === "ACTIVE" ? "secondary" : to === "ENDED" ? "destructive" : "secondary"} onClick={() => setChange(to)}>
              {STATUS_CONFIRM[to].confirm}
            </Button>
          ))}
        </div>
      </section>
      {departments.data && <DepartmentChange member={member} departments={departments.data.items} />}
      {member.status === "ACTIVE" && <Roles member={member} departments={departments.data?.items ?? []} />}
      {change && confirm && (
        <ConfirmDialog
          title={confirm.title}
          description={`${member.display_name}: ${confirm.description}`}
          confirmLabel={confirm.confirm}
          pendingLabel={confirm.pending}
          destructive={change !== "ACTIVE"}
          {...(confirm.reason ? { reasonLabel: "Reason (recorded in the audit log)" } : {})}
          pending={status.isPending}
          error={status.isError ? errorText(status.error) : null}
          onConfirm={(reason) => status.mutate({ to: change, reason })}
          onCancel={() => {
            setChange(null);
            status.reset();
          }}
        />
      )}
    </div>
  );
}

function DepartmentChange({ member, departments }: { member: Member; departments: Department[] }) {
  const id = useId();
  const changed = useMemberChanged();
  const [value, setValue] = useState(member.department?.id ?? "");
  const save = useMutation({ mutationFn: () => updateMember(member.id, { department_id: value }), onSuccess: changed });
  const error = save.isError ? errorText(save.error) : null;
  return (
    <section aria-label="Department" className="space-y-2">
      <label htmlFor={id} className="block text-sm font-semibold">
        Department
      </label>
      <div className="flex flex-wrap gap-3">
        <Select id={id} value={value} onChange={(e) => setValue(e.target.value)} className="w-auto min-w-48">
          {!member.department && <option value="">Choose a department</option>}
          {departments.map((d) => (
            <option key={d.id} value={d.id}>
              {d.code} · {d.name}
            </option>
          ))}
        </Select>
        <Button variant="secondary" onClick={() => save.mutate()} disabled={!value || value === member.department?.id || save.isPending}>
          {save.isPending ? "Saving…" : "Save department"}
        </Button>
      </div>
      {error && <Callout tone="danger">{error}</Callout>}
    </section>
  );
}

const ROLE_OPTIONS: { value: RoleName; label: string }[] = [
  { value: "COLLEGE_ADMIN", label: "College admin" },
  { value: "DEPARTMENT_ADMIN", label: "Department admin" },
  { value: "ISSUE_COORDINATOR", label: "Issue coordinator" },
];

function Roles({ member, departments }: { member: Member; departments: Department[] }) {
  const changed = useMemberChanged();
  const roleId = useId();
  const deptId = useId();
  const [role, setRole] = useState<RoleName>("DEPARTMENT_ADMIN");
  const [department, setDepartment] = useState("");
  const [revoking, setRevoking] = useState<Grant | null>(null);
  const grant = useMutation({
    mutationFn: () => grantRole(member.id, role === "DEPARTMENT_ADMIN" ? { role, department_id: department } : { role }),
    onSuccess: changed,
  });
  const revoke = useMutation({
    mutationFn: (g: Grant) => revokeRole(member.id, g.id),
    onSuccess: async () => {
      setRevoking(null);
      await changed();
    },
  });
  const grantError = grant.isError ? errorText(grant.error) : null;

  return (
    <section aria-label="Roles" className="space-y-3">
      <h3 className="text-sm font-semibold">Roles</h3>
      {member.roles.length === 0 ? (
        <p className="text-sm text-muted">No roles.</p>
      ) : (
        <ul className="space-y-2">
          {member.roles.map((g) => (
            <li key={g.id} className="flex flex-wrap items-center gap-3 text-sm">
              {roleLabel(g)}
              <Button size="sm" variant="ghost" aria-label={`Remove ${roleLabel(g)}`} onClick={() => setRevoking(g)}>
                Remove
              </Button>
            </li>
          ))}
        </ul>
      )}
      <div className="flex flex-wrap items-end gap-3">
        <div className="space-y-1.5">
          <label htmlFor={roleId} className="block text-sm font-medium">
            Give role
          </label>
          <Select id={roleId} value={role} onChange={(e) => setRole(e.target.value as RoleName)} className="w-auto">
            {ROLE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
        </div>
        {role === "DEPARTMENT_ADMIN" && (
          <div className="space-y-1.5">
            <label htmlFor={deptId} className="block text-sm font-medium">
              Of department
            </label>
            <Select id={deptId} value={department} onChange={(e) => setDepartment(e.target.value)} className="w-auto">
              <option value="">Choose</option>
              {departments.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.code}
                </option>
              ))}
            </Select>
          </div>
        )}
        <Button variant="secondary" onClick={() => grant.mutate()} disabled={grant.isPending || (role === "DEPARTMENT_ADMIN" && !department)}>
          {grant.isPending ? "Giving…" : "Give role"}
        </Button>
      </div>
      {grantError && <Callout tone="danger">{grantError}</Callout>}
      {revoking && (
        <ConfirmDialog
          title={`Remove ${roleLabel(revoking)}?`}
          description={`${member.display_name} loses what this role allows straight away.`}
          confirmLabel="Remove role"
          pendingLabel="Removing…"
          pending={revoke.isPending}
          error={revoke.isError ? errorText(revoke.error) : null}
          onConfirm={() => revoke.mutate(revoking)}
          onCancel={() => {
            setRevoking(null);
            revoke.reset();
          }}
        />
      )}
    </section>
  );
}
