import {
    Activity,
    ArrowDownToLine,
    ArrowLeft,
    ArrowRight,
    ChevronRight,
    CircleAlert,
    FileJson,
    FlaskConical,
    Folder,
    GitCompareArrows,
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
    ShieldCheck,
];
function pageFor(item: Item): Page {
    return item.kind === "suite"
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
    const [runOpen, setRunOpen] = useState(false),
        [newSuite, setNewSuite] = useState(false);
    const [theme, setTheme] = useState(
        localStorage.getItem("thadam-theme") || "dark",
    );
    const [busy, setBusy] = useState(false);
    const lastCompleted = useRef("");
    const dirty = useRef(false);
    const [detailLoading, setDetailLoading] = useState(false);
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
        setPage(next);
        setSelected(null);
        setArtifact(null);
        setSearch("");
        setStatus("all");
        setNewSuite(false);
    }
    function open(item: Item) {
        if (!canLeave()) return;
        setPage(pageFor(item));
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
            (page === "Suites" && item.kind === "suite") ||
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
    return (
        <div className="app-shell">
            <a className="skip-link" href="#main">
                Skip to content
            </a>
            <aside className="sidebar">
                <a
                    className="brand"
                    href="#"
                    onClick={(e) => {
                        e.preventDefault();
                        navigate("Overview");
                    }}
                >
                    <span className="brand-mark">
                        <Activity size={23} />
                    </span>
                    <span>
                        THADAM
                        <span className="brand-caption">
                            Agent testing, with evidence.
                        </span>
                    </span>
                </a>
                <div className="workspace">
                    <Folder size={16} />
                    <span>{catalog?.name || "Local workspace"}</span>
                    <span className="local-label">LOCAL</span>
                </div>
                <nav aria-label="Main navigation">
                    {pages.map((name, i) => {
                        const Icon = icons[i];
                        return (
                            <button
                                key={name}
                                className={
                                    "nav-item " +
                                    (page === name ? "active" : "")
                                }
                                onClick={() => navigate(name)}
                                aria-current={
                                    page === name ? "page" : undefined
                                }
                            >
                                <Icon size={18} />
                                {name}
                                {name === "Evaluations" && active && (
                                    <span className="live-dot" />
                                )}
                            </button>
                        );
                    })}
                </nav>
                <div className="sidebar-bottom">
                    <p>Every agent leaves a trace.</p>
                    <div className="connection">
                        <span className={connected ? "dot" : "dot off"} />
                        {connected
                            ? "Connected to your project"
                            : "Waiting for connection"}
                    </div>
                    <div className="sidebar-controls">
                        <Button
                            quiet
                            onClick={() =>
                                setTheme(theme === "dark" ? "light" : "dark")
                            }
                        >
                            {theme === "dark" ? (
                                <Sun size={16} />
                            ) : (
                                <Moon size={16} />
                            )}{" "}
                            {theme === "dark" ? "Light mode" : "Dark mode"}
                        </Button>
                    </div>
                </div>
            </aside>
            <div className="workspace-shell">
                <header className="topbar">
                    <span>
                        <Folder size={15} />
                        <span className="project-path" title={catalog?.root}>
                            {catalog?.name || "Your project"}
                        </span>
                        <ChevronRight size={14} />
                        <strong>{page}</strong>
                    </span>
                    <div className="topbar-actions">
                        <button
                            className="icon-button mobile-theme"
                            aria-label={
                                theme === "dark" ? "Light mode" : "Dark mode"
                            }
                            onClick={() =>
                                setTheme(theme === "dark" ? "light" : "dark")
                            }
                        >
                            {theme === "dark" ? (
                                <Sun size={16} />
                            ) : (
                                <Moon size={16} />
                            )}
                        </button>
                        <span className="local-indicator">Local workspace</span>
                        <Button
                            quiet
                            onClick={refresh}
                            disabled={busy || !connected}
                            title="Refresh saved files"
                        >
                            <RefreshCw
                                size={16}
                                className={busy ? "spin" : ""}
                            />
                            <span>Refresh</span>
                        </Button>
                        <Button
                            primary
                            onClick={() => {
                                navigate("Evaluations");
                                setRunOpen(true);
                            }}
                            disabled={!connected || !!active}
                        >
                            <Play size={14} />
                            Run evaluation
                        </Button>
                    </div>
                </header>
                <main id="main">
                    {error && (
                        <div className="dismiss-error">
                            <ErrorBox error={error} />
                            <button
                                aria-label="Dismiss error"
                                onClick={() => setError("")}
                            >
                                <X size={16} />
                            </button>
                        </div>
                    )}
                    {loading ? (
                        <div className="loading" role="status">
                            <RefreshCw className="spin" size={22} />
                            Opening your workspace…
                        </div>
                    ) : !connected ? (
                        <Empty title="Connect to your local project">
                            Keep the dashboard terminal open and use the link it
                            prints. Reports and agent code stay on your
                            computer.
                        </Empty>
                    ) : (
                        <>
                            {active && (
                                <div className="running-banner">
                                    <Activity size={17} />
                                    <div>
                                        <strong>Evaluation running</strong>
                                        <span>
                                            {active.completed}/{active.total}{" "}
                                            invocations completed
                                            {active.case
                                                ? " · " + active.case
                                                : ""}
                                        </span>
                                    </div>
                                    <Button
                                        quiet
                                        onClick={() => {
                                            navigate("Evaluations");
                                        }}
                                    >
                                        View progress
                                        <ArrowRight size={14} />
                                    </Button>
                                </div>
                            )}
                            {selected && !artifact ? (
                                detailLoading ? (
                                    <div className="loading">
                                        Loading saved evidence…
                                    </div>
                                ) : (
                                    <Empty
                                        title="This artifact could not be opened"
                                        action={
                                            <Button
                                                onClick={() => navigate(page)}
                                            >
                                                Back to files
                                            </Button>
                                        }
                                    >
                                        Check the error above, then refresh or
                                        choose another file.
                                    </Empty>
                                )
                            ) : artifact ? (
                                <>
                                    <div className="detail-toolbar">
                                        <Button
                                            quiet
                                            onClick={() => {
                                                if (canLeave()) {
                                                    setSelected(null);
                                                    setArtifact(null);
                                                }
                                            }}
                                        >
                                            <ArrowLeft size={15} />
                                            Back to {page.toLowerCase()}
                                        </Button>
                                        <div>
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
                                                <ArrowDownToLine size={15} />
                                                Download JSON
                                            </Button>
                                        </div>
                                    </div>
                                    {artifact.kind === "suite" ? (
                                        <SuiteEditor
                                            onDirty={(value) => {
                                                dirty.current = value;
                                            }}
                                            key={artifact.path}
                                            artifact={artifact}
                                            onSaved={async (data) => {
                                                dirty.current = false;
                                                await refresh();
                                                setArtifact(data);
                                                setSelected(data.path);
                                            }}
                                        />
                                    ) : (
                                        <ArtifactView
                                            artifact={artifact}
                                            catalog={catalog!}
                                            onOpen={open}
                                            onSaved={async (data) => {
                                                await refresh();
                                                open(data);
                                            }}
                                        />
                                    )}
                                </>
                            ) : newSuite ? (
                                <SuiteEditor
                                    onDirty={(value) => {
                                        dirty.current = value;
                                    }}
                                    onSaved={async (data) => {
                                        dirty.current = false;
                                        await refresh();
                                        open(data);
                                    }}
                                />
                            ) : (
                                <>
                                    <div className="page-heading">
                                        <div>
                                            <h1>
                                                {page === "Overview"
                                                    ? "A clear view of your agents."
                                                    : page}
                                            </h1>
                                            <p>
                                                {page === "Overview"
                                                    ? "Run with confidence. Find what changed. Follow the evidence."
                                                    : page === "Suites"
                                                      ? "Define the behavior your agent should meet."
                                                      : page === "Evaluations"
                                                        ? "Every case, every attempt, and the evidence behind it."
                                                        : page === "Comparisons"
                                                          ? "Understand what improved, what regressed, and what changed."
                                                          : "Review the evidence before accepting a new baseline."}
                                            </p>
                                        </div>
                                        {page === "Suites" && (
                                            <Button
                                                primary
                                                onClick={() =>
                                                    setNewSuite(true)
                                                }
                                            >
                                                <Plus size={15} />
                                                New suite
                                            </Button>
                                        )}
                                    </div>
                                    {page === "Overview" && (
                                        <>
                                            <div className="metric-strip">
                                                <div>
                                                    <span>
                                                        Saved evaluations
                                                    </span>
                                                    <strong>
                                                        {evaluations.length}
                                                    </strong>
                                                    <small>
                                                        Single and repeated
                                                        report files
                                                    </small>
                                                </div>
                                                <div>
                                                    <span>
                                                        Passed invocations
                                                    </span>
                                                    <strong className="teal">
                                                        {totals.passed}
                                                    </strong>
                                                    <small>
                                                        All checks passed
                                                    </small>
                                                </div>
                                                <div>
                                                    <span>
                                                        Failed invocations
                                                    </span>
                                                    <strong
                                                        className={
                                                            totals.failed
                                                                ? "amber"
                                                                : ""
                                                        }
                                                    >
                                                        {totals.failed}
                                                    </strong>
                                                    <small>
                                                        Expectations unmet
                                                    </small>
                                                </div>
                                                <div>
                                                    <span>
                                                        Execution errors
                                                    </span>
                                                    <strong
                                                        className={
                                                            totals.errors
                                                                ? "red"
                                                                : ""
                                                        }
                                                    >
                                                        {totals.errors}
                                                    </strong>
                                                    <small>
                                                        Execution or evaluation
                                                        errors
                                                    </small>
                                                </div>
                                            </div>
                                            <div className="section-heading">
                                                <h2>Recent activity</h2>
                                                <span>
                                                    {catalog?.items.length || 0}{" "}
                                                    saved artifacts
                                                </span>
                                            </div>
                                        </>
                                    )}
                                    {page === "Evaluations" && (
                                        <>
                                            <RunPanel
                                                open={runOpen}
                                                onToggle={() =>
                                                    setRunOpen(!runOpen)
                                                }
                                                catalog={catalog!}
                                                active={!!active}
                                                onStarted={(job) => {
                                                    setJobs([job, ...jobs]);
                                                    setRunOpen(false);
                                                }}
                                            />
                                            {jobs.length > 0 && (
                                                <JobList
                                                    jobs={jobs}
                                                    onRefresh={refresh}
                                                    onOpen={(path) => {
                                                        refresh();
                                                        setSelected(path);
                                                    }}
                                                />
                                            )}
                                        </>
                                    )}
                                    {page === "Comparisons" && (
                                        <ComparePanel
                                            catalog={catalog!}
                                            onSaved={async (path) => {
                                                await refresh();
                                                setSelected(path);
                                            }}
                                        />
                                    )}
                                    {page === "Baselines" && (
                                        <ReviewPanel
                                            catalog={catalog!}
                                            onSaved={async (data) => {
                                                await refresh();
                                                open(data);
                                            }}
                                        />
                                    )}
                                    <div className="library-controls">
                                        <div className="search">
                                            <Search size={16} />
                                            <input
                                                aria-label="Search saved files"
                                                value={search}
                                                onChange={(e) =>
                                                    setSearch(e.target.value)
                                                }
                                                placeholder="Search by file, suite, or revision…"
                                            />
                                            {search && (
                                                <button
                                                    aria-label="Clear search"
                                                    onClick={() =>
                                                        setSearch("")
                                                    }
                                                >
                                                    <X size={14} />
                                                </button>
                                            )}
                                        </div>
                                        <select
                                            aria-label="Filter by result"
                                            value={status}
                                            onChange={(e) =>
                                                setStatus(e.target.value)
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
                                            ].map((s) => (
                                                <option value={s} key={s}>
                                                    {s === "all"
                                                        ? "All results"
                                                        : s}
                                                </option>
                                            ))}
                                        </select>
                                    </div>
                                    {filtered.length ? (
                                        <ArtifactTable
                                            items={
                                                page === "Overview"
                                                    ? filtered.slice(0, 15)
                                                    : filtered
                                            }
                                            onOpen={open}
                                        />
                                    ) : (
                                        <Empty
                                            title={
                                                search || status !== "all"
                                                    ? "No matching results"
                                                    : page === "Suites"
                                                      ? "Your test cases start here"
                                                      : "Your evidence will appear here"
                                            }
                                            action={
                                                page === "Suites" ? (
                                                    <Button
                                                        primary
                                                        onClick={() =>
                                                            setNewSuite(true)
                                                        }
                                                    >
                                                        <Plus size={15} />
                                                        Create a suite
                                                    </Button>
                                                ) : undefined
                                            }
                                        >
                                            {search || status !== "all"
                                                ? "Try another search or choose All results."
                                                : "Save a Thadam suite or report inside this project, then refresh. Start an evaluation to create evidence."}
                                        </Empty>
                                    )}
                                    {catalog!.invalid.length > 0 && (
                                        <details className="invalid-files">
                                            <summary>
                                                <CircleAlert size={15} />
                                                {catalog!.invalid.length} files
                                                need attention
                                            </summary>
                                            {catalog!.invalid.map((item) => (
                                                <div key={item.path}>
                                                    <strong>{item.path}</strong>
                                                    <p>{item.error}</p>
                                                </div>
                                            ))}
                                        </details>
                                    )}
                                </>
                            )}
                        </>
                    )}
                    <footer>
                        <span>
                            THADAM <span className="footer-tamil">தடம்</span>
                        </span>
                        <span>Observable evidence. Explicit expectations.</span>
                    </footer>
                </main>
            </div>
        </div>
    );
}

function ArtifactTable({
    items,
    onOpen,
}: {
    items: Item[];
    onOpen: (item: Item) => void;
}) {
    return (
        <div className="table-scroll">
            <table className="artifact-table">
                <thead>
                    <tr>
                        <th>Artifact</th>
                        <th>Type</th>
                        <th>Result</th>
                        <th>Cases</th>
                        <th className="runtime-column">Runtime</th>
                        <th className="updated-column">File updated</th>
                        <th>
                            <span className="sr-only">Open</span>
                        </th>
                    </tr>
                </thead>
                <tbody>
                    {items.map((item) => (
                        <tr key={item.path}>
                            <td>
                                <button
                                    className="file-link"
                                    onClick={() => onOpen(item)}
                                >
                                    <FileJson size={17} />
                                    <span>
                                        <strong>
                                            {item.suite?.id ||
                                                titlePath(item.path)}
                                        </strong>
                                        <small>
                                            {item.path}
                                            {item.suite
                                                ? " · " + item.suite.revision
                                                : ""}
                                        </small>
                                    </span>
                                </button>
                            </td>
                            <td>
                                <span className="type-label">
                                    {kindName[item.kind] || item.kind}
                                </span>
                            </td>
                            <td>
                                <Badge status={outcome(item)} />
                                {item.summary && "passed" in item.summary && (
                                    <small className="row-outcomes">
                                        <span>
                                            {item.summary.passed} passed
                                        </span>
                                        <span
                                            className={
                                                item.summary.failed
                                                    ? "amber"
                                                    : ""
                                            }
                                        >
                                            {item.summary.failed} failed
                                        </span>
                                        <span
                                            className={
                                                item.summary.errors ? "red" : ""
                                            }
                                        >
                                            {item.summary.errors} errors
                                        </span>
                                    </small>
                                )}
                            </td>
                            <td className="numeric">{item.cases}</td>
                            <td className="runtime-column duration">
                                {item.duration_ms == null
                                    ? "Unavailable"
                                    : Number(String(item.duration_ms)).toFixed(
                                          2,
                                      ) + " ms"}
                            </td>
                            <td className="date updated-column">
                                {new Date(
                                    Number(String(item.modified_ns)) / 1e6,
                                ).toLocaleString(undefined, {
                                    month: "short",
                                    day: "numeric",
                                    hour: "2-digit",
                                    minute: "2-digit",
                                })}
                            </td>
                            <td>
                                <button
                                    className="icon-button"
                                    aria-label={"Open " + item.path}
                                    onClick={() => onOpen(item)}
                                >
                                    <ArrowRight size={16} />
                                </button>
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}
