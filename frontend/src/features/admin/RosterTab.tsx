import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Download, ListChecks } from "lucide-react";
import { useId, useState, type FormEvent } from "react";

import { Callout } from "@/components/Callout";
import { DataTable } from "@/components/DataTable";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { SubmitButton } from "@/components/SubmitButton";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api";
import { usePageTitle } from "@/lib/usePageTitle";

import { fetchRoster, importRoster, type RosterProblem } from "./api";
import { manageKeys } from "./keys";
import { errorText } from "./labels";
import { ListLoading, LoadMore } from "./list";
import { useCursorList } from "./useCursorList";

const COLUMNS = ["roll_number", "full_name", "department_code", "program", "admission_year", "email"];
const TEMPLATE = `${COLUMNS.join(",")}\nCSE2025001,Asha Rao,CSE,B.Tech Computer Science,2025,asha.rao@example.edu\n`;
const MAX_FILE_BYTES = 1_000_000;

function downloadTemplate() {
  const url = URL.createObjectURL(new Blob([TEMPLATE], { type: "text/csv" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = "roster-template.csv";
  link.click();
  URL.revokeObjectURL(url);
}

function problemsOf(error: unknown): RosterProblem[] {
  if (!(error instanceof ApiError) || error.code !== "roster_invalid" || !Array.isArray(error.details)) return [];
  return error.details as RosterProblem[];
}

/** Roster import (MEMBER-001, Design.md §5 screen 17): template, upload, row errors; then the list. */
export function RosterTab() {
  usePageTitle("Roster · Manage");
  return (
    <div className="space-y-8">
      <RosterImport />
      <RosterList />
    </div>
  );
}

function RosterImport() {
  const queryClient = useQueryClient();
  const fileId = useId();
  const pasteId = useId();
  const [csv, setCsv] = useState("");
  const [fileName, setFileName] = useState<string | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);
  const run = useMutation({
    mutationFn: importRoster,
    onSuccess: async () => {
      setCsv("");
      setFileName(null);
      await queryClient.invalidateQueries({ queryKey: manageKeys.roster });
    },
  });
  const problems = problemsOf(run.error);
  const failure = run.isError && problems.length === 0 ? errorText(run.error) : null;

  const onFile = async (file: File | undefined) => {
    run.reset();
    setLocalError(null);
    if (!file) return;
    if (file.size > MAX_FILE_BYTES) {
      setLocalError("The file is larger than 1 MB. Split it into smaller files.");
      return;
    }
    setFileName(file.name);
    setCsv(await file.text());
  };
  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (!csv.trim()) {
      setLocalError("Choose a CSV file or paste the rows.");
      return;
    }
    setLocalError(null);
    run.mutate(csv);
  };

  return (
    <section aria-labelledby="roster-import" className="space-y-4">
      <h2 id="roster-import" className="text-lg font-semibold">
        Import students
      </h2>
      <div className="space-y-2 text-sm text-muted">
        <p>
          A CSV file with the columns <span className="font-mono text-fg">{COLUMNS.join(", ")}</span>. Email can be empty. If any row has a problem, nothing is imported, so fix the rows listed and try again.
        </p>
        <Button size="sm" variant="secondary" onClick={downloadTemplate}>
          <Download aria-hidden="true" strokeWidth={1.5} />
          Download template
        </Button>
      </div>
      <form noValidate onSubmit={onSubmit} className="space-y-4">
        {localError && <Callout tone="danger">{localError}</Callout>}
        {failure && <Callout tone="danger">{failure}</Callout>}
        {run.isSuccess && <Callout tone="success">Imported {run.data.imported} students.</Callout>}
        {problems.length > 0 && (
          <div className="space-y-3">
            <Callout tone="danger" title="Nothing was imported.">
              <p>Fix these rows and import the file again. Row 1 is the header.</p>
            </Callout>
            <DataTable
              caption="Problems in the file"
              rows={problems}
              rowKey={(p) => `${p.row}-${p.column ?? ""}-${p.message}`}
              columns={[
                { header: "Row", cell: (p) => p.row },
                { header: "Column", cell: (p) => (p.column ? <span className="font-mono">{p.column}</span> : "Whole file") },
                { header: "Problem", cell: (p) => p.message },
              ]}
            />
          </div>
        )}
        <div className="space-y-1.5">
          <label htmlFor={fileId} className="block text-sm font-medium">
            CSV file
          </label>
          <input
            id={fileId}
            type="file"
            accept=".csv,text/csv"
            onChange={(e) => void onFile(e.target.files?.[0])}
            className="block w-full text-sm text-muted file:mr-3 file:h-10 file:rounded-sm file:border file:border-border-strong file:bg-surface file:px-4 file:text-sm file:font-medium file:text-fg"
          />
          {fileName && <p className="text-sm text-muted">{fileName} is ready to import.</p>}
        </div>
        <div className="space-y-1.5">
          <label htmlFor={pasteId} className="block text-sm font-medium">
            Or paste the rows
          </label>
          <Textarea
            id={pasteId}
            spellCheck={false}
            className="font-mono text-sm"
            value={csv}
            onChange={(e) => {
              setCsv(e.target.value);
              setFileName(null);
            }}
          />
        </div>
        <SubmitButton pending={run.isPending} pendingLabel="Importing…">
          Import
        </SubmitButton>
      </form>
    </section>
  );
}

function RosterList() {
  const searchId = useId();
  const [draft, setDraft] = useState("");
  const [search, setSearch] = useState("");
  const { query, items } = useCursorList([...manageKeys.roster, search], (cursor, signal) => fetchRoster(search, cursor, signal));

  return (
    <section aria-labelledby="roster-heading" className="space-y-3">
      <h2 id="roster-heading" className="text-lg font-semibold">
        Roster
      </h2>
      <form
        role="search"
        onSubmit={(event) => {
          event.preventDefault();
          setSearch(draft.trim());
        }}
        className="flex items-end gap-2"
      >
        <div className="flex-1 space-y-1.5">
          <label htmlFor={searchId} className="block text-sm font-medium">
            Search
          </label>
          <Input id={searchId} type="search" placeholder="Roll number or name" value={draft} onChange={(e) => setDraft(e.target.value)} />
        </div>
        <Button type="submit" variant="secondary">
          Search
        </Button>
      </form>
      {query.isPending ? (
        <ListLoading label="Loading the roster" />
      ) : query.isError ? (
        <ErrorState title="Couldn't load the roster." error={query.error} onRetry={() => void query.refetch()} retrying={query.isFetching} />
      ) : items.length === 0 ? (
        <EmptyState Icon={ListChecks} title={search ? `No students match “${search}”.` : "The roster is empty."}>
          {!search && "Students can join once their roll number is on the roster."}
        </EmptyState>
      ) : (
        <>
          <DataTable
            caption="Roster"
            rows={items}
            rowKey={(r) => r.id}
            columns={[
              { header: "Roll number", cell: (r) => <span className="font-mono">{r.roll_number}</span> },
              { header: "Name", cell: (r) => r.full_name },
              { header: "Department", cell: (r) => r.department.code },
              { header: "Programme", cell: (r) => `${r.program} · ${r.admission_year}` },
              { header: "Email", cell: (r) => (r.email ? <span className="break-all">{r.email}</span> : <span className="text-muted">None</span>) },
              { header: "Joined", cell: (r) => (r.claimed ? "Yes" : "Not yet") },
            ]}
          />
          <LoadMore shown={items.length} hasMore={query.hasNextPage} loading={query.isFetchingNextPage} onLoad={() => void query.fetchNextPage()} />
        </>
      )}
    </section>
  );
}
