import {
    Activity,
    ArrowDownToLine,
    ArrowLeft,
    ChevronRight,
    CircleAlert,
    PanelLeftClose,
    PanelLeftOpen,
    FileJson,
    FlaskConical,
    Folder,
    GitCompareArrows,
    WandSparkles,
    LayoutDashboard,
    Moon,
    Play,
    Plus,
    RefreshCw,
    Search,
    ShieldCheck,
    Sun,
    X,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import {
    api,
    kindName,
    outcome,
    type Artifact,
    type Catalog,
    type Data,
    type Item,
} from "./api";
import { ArtifactView } from "./artifact";
import { ReviewPanel } from "./baselines";
import { ComparePanel } from "./comparisons";
import {
    Badge,
    Button,
    Copy,
    Empty,
    ErrorBox,
    exportArtifact,
    titlePath,
} from "./components";
import { JobList, RunPanel } from "./evaluations";
import { SuiteEditor } from "./suites";
import { SuggestPanel, DraftReview } from "./generation";
const pages = [
    "Overview",
    "Suites",
    "Evaluations",
    "Comparisons",
    "Baselines",
] as const;
type Page = (typeof pages)[number];
const icons = [
    LayoutDashboard,
    FileJson,
    FlaskConical,
    GitCompareArrows,
    WandSparkles,
    ShieldCheck,
];
function pageFor(item: Item): Page {
    return ["suite", "scenario_draft"].includes(item.kind)
        ? "Suites"
        : item.kind.includes("comparison")
          ? "Comparisons"
          : item.kind.includes("baseline")
            ? "Baselines"
            : "Evaluations";
}

export function App() {
    const initial = new URLSearchParams(location.hash.slice(1));
    const [page, setPage] = useState<Page>(
        pages.includes(initial.get("page") as Page)
            ? (initial.get("page") as Page)
            : "Overview",
    );
    const [selected, setSelected] = useState<string | null>(
        initial.get("file"),
    );
    const [catalog, setCatalog] = useState<Catalog | null>(null),
        [artifact, setArtifact] = useState<Artifact | null>(null);
    const [error, setError] = useState(""),
        [loading, setLoading] = useState(true),
        [connected, setConnected] = useState(false);
    const [search, setSearch] = useState(""),
        [status, setStatus] = useState("all"),
        [jobs, setJobs] = useState<Data[]>([]);
    const [action, setAction] = useState<
        "run" | "compare" | "review" | "suggest" | null
    >(null);
    const [newSuite, setNewSuite] = useState(false);
    const [libraryOpen, setLibraryOpen] = useState(true);
    const inspector = useRef<HTMLElement>(null);
    const [theme, setTheme] = useState(
        localStorage.getItem("thadam-theme") || "dark",
    );
    const [busy, setBusy] = useState(false);
    const lastCompleted = useRef("");
    const dirty = useRef(false);
    const [detailLoading, setDetailLoading] = useState(false);
    useEffect(() => {
        window.scrollTo(0, 0);
        if (inspector.current) inspector.current.scrollTop = 0;
    }, [page, selected, newSuite, action]);
    useEffect(() => {
        document.documentElement.dataset.theme = theme;
        localStorage.setItem("thadam-theme", theme);
    }, [theme]);
    async function refresh() {
        setBusy(true);
        try {
            setCatalog(await api<Catalog>("workspace"));
            setError("");
        } catch (e) {
            setError((e as Error).message);
        } finally {
            setBusy(false);
            setLoading(false);
        }
    }
    useEffect(() => {
        let cancelled = false;
        (async () => {
            try {
                const token = initial.get("token");
                if (token) {
                    const r = await fetch("/api/session", {
                        method: "POST",
                        headers: { "x-thadam-token": token },
                    });
                    if (!r.ok)
                        throw new Error(
                            "This session link expired. Open the current link from your terminal.",
                        );
                    history.replaceState(null, "", location.pathname);
                }
                await api("workspace");
                if (!cancelled) {
                    setConnected(true);
                    await refresh();
                }
            } catch (e) {
                if (!cancelled) {
                    setError((e as Error).message);
                    setLoading(false);
                }
            }
        })();
        return () => {
            cancelled = true;
        };
    }, []);
    useEffect(() => {
        if (!connected) return;
        let alive = true;
        const update = async () => {
            try {
                const list = await api<Data[]>("jobs");
                if (alive) setJobs(list);
            } catch {}
        };
        update();
        const timer = setInterval(update, 1000);
        return () => {
            alive = false;
            clearInterval(timer);
        };
    }, [connected]);
    useEffect(() => {
        if (!connected) return;
        const params = new URLSearchParams({ page });
        if (selected) params.set("file", selected);
        history.replaceState(null, "", "#" + params.toString());
    }, [page, selected, connected]);
    useEffect(() => {
        setArtifact(null);
        if (!selected || !connected) return;
        setDetailLoading(true);
        let alive = true;
        api<Artifact>("artifact?path=" + encodeURIComponent(selected))
            .then((data) => {
                if (alive) setArtifact(data);
            })
            .catch((e) => {
                if (alive) setError(e.message);
            })
            .finally(() => {
                if (alive) setDetailLoading(false);
            });
        return () => {
            alive = false;
        };
    }, [selected, connected]);
    function canLeave() {
        if (
            !dirty.current ||
            window.confirm("Discard unsaved suite changes?")
        ) {
            dirty.current = false;
            return true;
        }
        return false;
    }
    function navigate(next: Page) {
        if (!canLeave()) return;
        setAction(null);
        setPage(next);
        setSelected(null);
        setArtifact(null);
        setSearch("");
        setStatus("all");
        setNewSuite(false);
    }
    function open(item: Item) {
        if (item.path === selected && !action && !newSuite) return;
        if (!canLeave()) return;
        setAction(null);
        if (page !== "Overview") setPage(pageFor(item));
        setSelected(item.path);
        setNewSuite(false);
        setError("");
    }
    useEffect(() => {
        const job = jobs[0];
        if (job?.state === "completed" && job.id !== lastCompleted.current) {
            lastCompleted.current = job.id;
            refresh();
        }
    }, [jobs[0]?.id, jobs[0]?.state]);
    const active = jobs.find((job) => job.state === "running");
    const items = (catalog?.items || []).filter(
        (item) =>
            page === "Overview" ||
            (page === "Suites" &&
                ["suite", "scenario_draft"].includes(item.kind)) ||
            (page === "Evaluations" &&
                ["run", "repeated_run"].includes(item.kind)) ||
            (page === "Comparisons" && item.kind.includes("comparison")) ||
            (page === "Baselines" && item.kind.includes("baseline")),
    );
    const filtered = items.filter(
        (item) =>
            (
                item.path +
                " " +
                (item.suite?.id || "") +
                " " +
                (item.suite?.revision || "")
            )
                .toLowerCase()
                .includes(search.toLowerCase()) &&
            (status === "all" || outcome(item) === status),
    );
    const evaluations = (catalog?.items || []).filter((item) =>
        ["run", "repeated_run"].includes(item.kind),
    );
    const totals = evaluations.reduce(
        (n, item) => ({
            passed: n.passed + (item.summary?.passed || 0),
            failed: n.failed + (item.summary?.failed || 0),
            errors: n.errors + (item.summary?.errors || 0),
        }),
        { passed: 0, failed: 0, errors: 0 },
    );
    useEffect(() => {
        if (
            !selected &&
            !action &&
            !newSuite &&
            filtered.length &&
            window.innerWidth >= 960 &&
            !dirty.current
        )
            setSelected(filtered[0].path);
    }, [page, catalog, selected, action, newSuite]);
    function startAction(next: "run" | "compare" | "review" | "suggest") {
        if (!canLeave()) return;
        setPage(
            next === "suggest"
                ? "Suites"
                : next === "run"
                  ? "Evaluations"
                  : next === "compare"
                    ? "Comparisons"
                    : "Baselines",
        );
        setSelected(null);
        setArtifact(null);
        setNewSuite(false);
        setAction(next);
        setSearch("");
        setStatus("all");
    }
    async function saved(next: Artifact) {
        dirty.current = false;
        setAction(null);
        setNewSuite(false);
        if (page !== "Overview") setPage(pageFor(next));
        setSelected(next.path);
        setArtifact(next);
        await refresh();
    }
    const PageIcon = icons[pages.indexOf(page)];
    const showingDetail = !!selected || !!action || newSuite;
    return (
        <div className="app-shell">
            <a className="skip-link" href="#main">
                Skip to content
            </a>
            <aside className="sidebar">
                <a
                    className="brand"
                    href="#"
                    aria-label="Thadam overview"
                    title="Thadam · தடம்"
                    onClick={(event) => {
                        event.preventDefault();
                        navigate("Overview");
                    }}
                >
                    <span className="brand-letter" lang="ta">
                        த
                    </span>
                </a>
                <nav aria-label="Main navigation">
                    {pages.map((name, index) => {
                        const Icon = icons[index];
                        return (
                            <button
                                key={name}
                                className={
                                    "nav-item " +
                                    (page === name ? "active" : "")
                                }
                                aria-label={name}
                                title={name}
                                aria-current={
                                    page === name ? "page" : undefined
                                }
                                onClick={() => navigate(name)}
                            >
                                <Icon size={17} strokeWidth={1.5} />
                                <span className="nav-label">{name}</span>
                                {name === "Evaluations" && active && (
                                    <span className="live-dot" />
                                )}
                            </button>
                        );
                    })}
                </nav>
                <div className="sidebar-bottom">
                    <span
                        className={
                            "session-dot " + (connected ? "connected" : "")
                        }
                        role="status"
                        aria-label={
                            connected
                                ? "Local session connected"
                                : "Not connected"
                        }
                        title={
                            connected
                                ? "Local session connected"
                                : "Not connected"
                        }
                    />
                    <button
                        className="icon-button"
                        aria-label={
                            theme === "dark" ? "Light mode" : "Dark mode"
                        }
                        title={theme === "dark" ? "Light mode" : "Dark mode"}
                        onClick={() =>
                            setTheme(theme === "dark" ? "light" : "dark")
                        }
                    >
                        {theme === "dark" ? (
                            <Sun size={16} strokeWidth={1.5} />
                        ) : (
                            <Moon size={16} strokeWidth={1.5} />
                        )}
                    </button>
                </div>
            </aside>
            <div className="workspace-shell">
                <header className="topbar">
                    <div className="workspace-breadcrumb">
                        <PageIcon size={15} strokeWidth={1.5} />
                        <strong>
                            {page === "Overview" ? "Project evidence" : page}
                        </strong>
                        <ChevronRight size={12} />
                        <span className="project-path" title={catalog?.root}>
                            {catalog?.name || "Local project"}
                        </span>
                    </div>
                    <div className="topbar-actions">
                        {active && (
                            <button
                                className="active-job-link"
                                onClick={() => startAction("run")}
                            >
                                <Activity size={13} />
                                {active.completed}/{active.total} running
                            </button>
                        )}
                        <button
                            className="icon-button"
                            aria-label="Refresh saved files"
                            title="Refresh saved files"
                            disabled={busy || !connected}
                            onClick={refresh}
                        >
                            <RefreshCw
                                size={14}
                                className={busy ? "spin" : ""}
                            />
                        </button>
                        <Button
                            primary
                            onClick={() => startAction("run")}
                            disabled={!connected || !!active}
                        >
                            <Play size={12} />
                            Run evaluation
                        </Button>
                    </div>
                </header>
                {error && (
                    <div className="dismiss-error">
                        <ErrorBox error={error} />
                        <button
                            className="icon-button"
                            aria-label="Dismiss error"
                            onClick={() => setError("")}
                        >
                            <X size={14} />
                        </button>
                    </div>
                )}
                {!connected ? (
                    <main id="main" className="connection-state">
                        {loading ? (
                            <div className="loading" role="status">
                                <RefreshCw size={17} className="spin" />
                                Opening project…
                            </div>
                        ) : (
                            <Empty title="Connect to your local project">
                                Keep the dashboard terminal open and use the
                                link it prints.
                            </Empty>
                        )}
                    </main>
                ) : (
                    <main
                        id="main"
                        className={
                            "workbench " +
                            (showingDetail ? "detail-open " : "") +
                            (!libraryOpen ? "library-collapsed" : "")
                        }
                    >
                        <section
                            className="artifact-library"
                            aria-label="Saved evidence"
                        >
                            <div className="library-heading">
                                <h1>
                                    {page === "Overview"
                                        ? "Saved evidence"
                                        : page}
                                </h1>
                                <span className="library-count">
                                    {items.length}
                                </span>
                                {page === "Suites" && (
                                    <Button
                                        quiet
                                        disabled={!!active}
                                        onClick={() => startAction("suggest")}
                                    >
                                        <WandSparkles size={13} />
                                        Suggest
                                    </Button>
                                )}
                                {page === "Suites" && (
                                    <Button
                                        quiet
                                        onClick={() => {
                                            if (canLeave()) {
                                                setNewSuite(true);
                                                setSelected(null);
                                                setArtifact(null);
                                                setAction(null);
                                            }
                                        }}
                                    >
                                        <Plus size={13} />
                                        New
                                    </Button>
                                )}
                                {page === "Comparisons" && (
                                    <Button
                                        quiet
                                        onClick={() => startAction("compare")}
                                    >
                                        <Plus size={13} />
                                        Compare
                                    </Button>
                                )}
                                {page === "Baselines" && (
                                    <Button
                                        quiet
                                        onClick={() => startAction("review")}
                                    >
                                        <Plus size={13} />
                                        Review
                                    </Button>
                                )}
                            </div>
                            <div className="library-controls">
                                <div className="search">
                                    <Search size={13} />
                                    <input
                                        aria-label="Search saved files"
                                        placeholder="Search files, suites, revisions…"
                                        value={search}
                                        onChange={(event) =>
                                            setSearch(event.target.value)
                                        }
                                    />
                                    {search && (
                                        <button
                                            aria-label="Clear search"
                                            onClick={() => setSearch("")}
                                        >
                                            <X size={12} />
                                        </button>
                                    )}
                                </div>
                                <select
                                    aria-label="Filter by result"
                                    value={status}
                                    onChange={(event) =>
                                        setStatus(event.target.value)
                                    }
                                >
                                    {[
                                        "all",
                                        "passed",
                                        "failed",
                                        "error",
                                        "blocked",
                                        "incompatible",
                                        "ready",
                                        "approved",
                                        "review required",
                                    ].map((value) => (
                                        <option key={value} value={value}>
                                            {value === "all"
                                                ? "All results"
                                                : value}
                                        </option>
                                    ))}
                                </select>
                            </div>
                            {page === "Overview" && (
                                <div
                                    className="library-summary"
                                    title="Invocation counts across saved evaluation files; every repeated attempt counts."
                                >
                                    <span>
                                        {evaluations.length} evaluations
                                    </span>
                                    <span>
                                        <b className="teal">{totals.passed}</b>{" "}
                                        passed
                                    </span>
                                    <span>
                                        <b
                                            className={
                                                totals.failed ? "amber" : ""
                                            }
                                        >
                                            {totals.failed}
                                        </b>{" "}
                                        failed
                                    </span>
                                    <span>
                                        <b
                                            className={
                                                totals.errors ? "red" : ""
                                            }
                                        >
                                            {totals.errors}
                                        </b>{" "}
                                        errors
                                    </span>
                                </div>
                            )}
                            <div className="library-column-labels">
                                <span>File / suite</span>
                                <span>Result · runtime</span>
                            </div>
                            <div className="library-scroll">
                                <ArtifactList
                                    items={filtered}
                                    selected={selected}
                                    onOpen={open}
                                />
                                {!filtered.length && (
                                    <div className="library-empty">
                                        <p>
                                            {search || status !== "all"
                                                ? "No matching files"
                                                : "No saved evidence yet"}
                                        </p>
                                        <small>
                                            {search || status !== "all"
                                                ? "Try another search or All results."
                                                : "Save a suite or report in this project, then refresh."}
                                        </small>
                                        {page === "Suites" && (
                                            <Button
                                                onClick={() => {
                                                    if (canLeave()) {
                                                        setNewSuite(true);
                                                        setSelected(null);
                                                        setArtifact(null);
                                                        setAction(null);
                                                    }
                                                }}
                                            >
                                                <Plus size={13} />
                                                Create a suite
                                            </Button>
                                        )}
                                    </div>
                                )}
                                {!!catalog?.invalid.length && (
                                    <details className="invalid-files">
                                        <summary>
                                            <CircleAlert size={13} />
                                            {catalog.invalid.length} files need
                                            attention
                                        </summary>
                                        {catalog.invalid.map((item) => (
                                            <div key={item.path}>
                                                <strong>{item.path}</strong>
                                                <p>{item.error}</p>
                                            </div>
                                        ))}
                                    </details>
                                )}
                            </div>
                            <div className="library-footer">
                                <span>
                                    {filtered.length}{" "}
                                    {filtered.length === 1 ? "file" : "files"}
                                </span>
                                <span title={catalog?.root}>
                                    <Folder size={11} />
                                    Local project
                                </span>
                            </div>
                        </section>
                        <section
                            className="detail-pane"
                            aria-label="Selected evidence"
                        >
                            <div className="inspector-toolbar">
                                <div className="inspector-location">
                                    <button
                                        className="icon-button desktop-pane-toggle"
                                        aria-label={
                                            libraryOpen
                                                ? "Hide file list"
                                                : "Show file list"
                                        }
                                        title={
                                            libraryOpen
                                                ? "Hide file list"
                                                : "Show file list"
                                        }
                                        onClick={() =>
                                            setLibraryOpen(!libraryOpen)
                                        }
                                    >
                                        {libraryOpen ? (
                                            <PanelLeftClose size={14} />
                                        ) : (
                                            <PanelLeftOpen size={14} />
                                        )}
                                    </button>
                                    <button
                                        className="icon-button mobile-back"
                                        aria-label="Back to files"
                                        onClick={() => {
                                            if (canLeave()) {
                                                setSelected(null);
                                                setArtifact(null);
                                                setAction(null);
                                                setNewSuite(false);
                                                setLibraryOpen(true);
                                            }
                                        }}
                                    >
                                        <ArrowLeft size={15} />
                                    </button>
                                    <span title={selected || undefined}>
                                        {selected
                                            ? titlePath(selected)
                                            : action === "suggest"
                                              ? "Suggest test cases"
                                              : action === "run"
                                                ? "Run evaluation"
                                                : action === "compare"
                                                  ? "Compare evaluations"
                                                  : action === "review"
                                                    ? "Review baseline"
                                                    : newSuite
                                                      ? "New suite"
                                                      : "Details"}
                                    </span>
                                </div>
                                {artifact && !action && !newSuite && (
                                    <div className="inspector-actions">
                                        <Copy
                                            value={artifact.path}
                                            label="Copy path"
                                        />
                                        <Button
                                            quiet
                                            onClick={() =>
                                                exportArtifact(artifact)
                                            }
                                        >
                                            <ArrowDownToLine size={13} />
                                            JSON
                                        </Button>
                                    </div>
                                )}
                            </div>
                            <section
                                className="inspector-content"
                                ref={inspector}
                            >
                                {action === "suggest" ? (
                                    <>
                                        <SuggestPanel
                                            catalog={catalog!}
                                            active={!!active}
                                            onDirty={(value) => {
                                                dirty.current = value;
                                            }}
                                            onStarted={(job) =>
                                                setJobs([job, ...jobs])
                                            }
                                        />
                                        <JobList
                                            jobs={jobs.filter(
                                                (job) =>
                                                    job.settings.kind ===
                                                    "generation",
                                            )}
                                            onRefresh={refresh}
                                            onOpen={(path) => {
                                                if (canLeave()) {
                                                    setAction(null);
                                                    setSelected(path);
                                                    refresh();
                                                }
                                            }}
                                        />
                                    </>
                                ) : action === "run" ? (
                                    <>
                                        <RunPanel
                                            open
                                            onToggle={() => setAction(null)}
                                            catalog={catalog!}
                                            active={!!active}
                                            onStarted={(job) =>
                                                setJobs([job, ...jobs])
                                            }
                                        />
                                        <JobList
                                            jobs={jobs}
                                            onRefresh={refresh}
                                            onOpen={(path) => {
                                                if (canLeave()) {
                                                    setAction(null);
                                                    setSelected(path);
                                                    refresh();
                                                }
                                            }}
                                        />
                                    </>
                                ) : action === "compare" ? (
                                    <ComparePanel
                                        initiallyOpen
                                        catalog={catalog!}
                                        onSaved={async (path) => {
                                            await refresh();
                                            setAction(null);
                                            setSelected(path);
                                        }}
                                    />
                                ) : action === "review" ? (
                                    <ReviewPanel
                                        initiallyOpen
                                        catalog={catalog!}
                                        onSaved={saved}
                                    />
                                ) : newSuite ? (
                                    <SuiteEditor
                                        onDirty={(value) => {
                                            dirty.current = value;
                                        }}
                                        onSaved={saved}
                                    />
                                ) : selected && (detailLoading || !artifact) ? (
                                    <div className="inspector-empty">
                                        {detailLoading ? (
                                            <p role="status">
                                                Loading saved evidence…
                                            </p>
                                        ) : (
                                            <>
                                                <h2>
                                                    This file could not be
                                                    opened
                                                </h2>
                                                <p>
                                                    Check the error above,
                                                    refresh, or select another
                                                    file.
                                                </p>
                                            </>
                                        )}
                                    </div>
                                ) : artifact ? (
                                    artifact.kind === "scenario_draft" ? (
                                        <DraftReview
                                            key={artifact.path}
                                            artifact={artifact}
                                            onUpdated={(next) => {
                                                setArtifact(next);
                                                refresh();
                                            }}
                                            onSaved={saved}
                                            onDirty={(value) => {
                                                dirty.current = value;
                                            }}
                                        />
                                    ) : artifact.kind === "suite" ? (
                                        <SuiteEditor
                                            key={
                                                artifact.path +
                                                artifact.fingerprint
                                            }
                                            artifact={artifact}
                                            onDirty={(value) => {
                                                dirty.current = value;
                                            }}
                                            onSaved={saved}
                                        />
                                    ) : (
                                        <ArtifactView
                                            key={artifact.path}
                                            artifact={artifact}
                                            catalog={catalog!}
                                            onOpen={open}
                                            onSaved={saved}
                                        />
                                    )
                                ) : (
                                    <div className="inspector-empty">
                                        <FileJson size={22} strokeWidth={1} />
                                        <h2>Select a saved file</h2>
                                        <p>
                                            Inspect cases, checks and recorded
                                            execution evidence here.
                                        </p>
                                        <span>
                                            thadam <span lang="ta">தடம்</span>
                                        </span>
                                    </div>
                                )}
                            </section>
                            {artifact && !action && !newSuite && (
                                <div className="inspector-footer">
                                    <span>
                                        {kindName[artifact.kind] ||
                                            artifact.kind}
                                    </span>
                                    <span>
                                        File updated{" "}
                                        {new Date(
                                            Number(
                                                String(artifact.modified_ns),
                                            ) / 1e6,
                                        ).toLocaleString(undefined, {
                                            month: "short",
                                            day: "numeric",
                                            hour: "2-digit",
                                            minute: "2-digit",
                                        })}
                                    </span>
                                </div>
                            )}
                        </section>
                    </main>
                )}
            </div>
        </div>
    );
}

function ArtifactList({
    items,
    selected,
    onOpen,
}: {
    items: Item[];
    selected: string | null;
    onOpen: (item: Item) => void;
}) {
    return (
        <div className="artifact-list">
            {items.map((item) => (
                <button
                    key={item.path}
                    className={
                        "artifact-row " +
                        (selected === item.path ? "selected" : "")
                    }
                    aria-label={"Open " + item.path}
                    aria-current={selected === item.path ? "true" : undefined}
                    onClick={() => onOpen(item)}
                >
                    <div className="artifact-row-main">
                        <strong title={item.path}>
                            {titlePath(item.path)}
                        </strong>
                        <span className="artifact-row-meta">
                            <span>
                                {item.suite?.id ||
                                    kindName[item.kind] ||
                                    item.kind}
                            </span>
                            {item.suite && (
                                <span className="revision-label">
                                    {item.suite.revision}
                                </span>
                            )}
                        </span>
                    </div>
                    <div className="artifact-row-result">
                        <Badge status={outcome(item)} />
                        <span>
                            {item.duration_ms == null
                                ? `${item.cases} ${item.cases === 1 ? "case" : "cases"}`
                                : Number(String(item.duration_ms)).toFixed(2) +
                                  " ms"}
                        </span>
                    </div>
                    <span className="sr-only">
                        {kindName[item.kind] || item.kind}. {item.cases} cases.{" "}
                        {item.summary && "passed" in item.summary
                            ? `${item.summary.passed} passed, ${item.summary.failed} failed, ${item.summary.errors} errors.`
                            : ""}{" "}
                        File updated{" "}
                        {new Date(
                            Number(String(item.modified_ns)) / 1e6,
                        ).toLocaleString()}
                        .
                    </span>
                </button>
            ))}
        </div>
    );
}
