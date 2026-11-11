import { Field } from "./components";

export const emptyBoundary = {
    turns: "",
    timeout: "",
    cleanup: "1",
    environment: "",
};
export type BoundarySettings = typeof emptyBoundary;

export function boundaryRequest(value: BoundarySettings, fixtures: boolean) {
    return {
        ...(value.turns || value.timeout
            ? {
                  execution_limits: {
                      max_turns: value.turns ? Number(value.turns) : null,
                      timeout_seconds: value.timeout
                          ? Number(value.timeout)
                          : null,
                      cleanup_timeout_seconds: Number(value.cleanup),
                  },
              }
            : {}),
        ...(fixtures && value.environment
            ? { environment: value.environment }
            : {}),
    };
}

export function ExecutionBoundaryFields({
    value,
    onChange,
    fixtures,
}: {
    value: BoundarySettings;
    onChange: (value: BoundarySettings) => void;
    fixtures: boolean;
}) {
    return (
        <>
            <Field
                label="Maximum conversation turns"
                hint="Optional. Stops before the next excess scripted turn and records an execution error."
            >
                <input
                    type="number"
                    min={1}
                    step={1}
                    value={value.turns}
                    onChange={(e) =>
                        onChange({ ...value, turns: e.target.value })
                    }
                />
            </Field>
            <Field
                label="Case deadline (seconds)"
                hint="Optional. Each case uses a fresh process; shared Python state is not retained between cases. Requires importable agents and verifiers."
            >
                <input
                    type="number"
                    min={0.01}
                    step="any"
                    value={value.timeout}
                    onChange={(e) =>
                        onChange({ ...value, timeout: e.target.value })
                    }
                />
            </Field>
            <Field
                label="Cleanup grace (seconds)"
                hint="Time allowed after a deadline for cleanup and worker termination. Forced termination can prevent cleanup from finishing."
            >
                <input
                    type="number"
                    min={0}
                    step="any"
                    disabled={!value.timeout}
                    value={value.cleanup}
                    onChange={(e) =>
                        onChange({ ...value, cleanup: e.target.value })
                    }
                />
            </Field>
            {fixtures && (
                <Field
                    label="Environment hooks"
                    hint="Optional module:hooks reference. Setup, reset and cleanup run for every case attempt."
                >
                    <input
                        value={value.environment}
                        placeholder="my_agent:environment"
                        onChange={(e) =>
                            onChange({ ...value, environment: e.target.value })
                        }
                    />
                </Field>
            )}
        </>
    );
}
