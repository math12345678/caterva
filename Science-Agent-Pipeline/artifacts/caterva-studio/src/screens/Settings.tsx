/**
 * /settings: the theme, how many runs work at once, whether deleting a run
 * asks first, offline mode, which GROMACS to use, and where the workspace
 * is.
 *
 * The theme applies the moment it is chosen (and is stored at once); the
 * others are saved together with the Save button, and a value the
 * server refuses comes back under its field in the server's words. Keys
 * the server stores that this page does not edit are sent back unchanged,
 * so a newer server's settings survive an older page.
 */
import { useEffect, useState } from "react";

import type { Settings } from "@/api/types";
import { Field, fieldError, FormActions, Select, Switch, TextInput } from "@/components/forms/Field";
import { useCommand } from "@/components/palette/commands";
import { Screen, Section } from "@/components/screen/Screen";
import { ThemeSwitch } from "@/components/shell/ThemeSwitch";
import { Loading } from "@/components/states/Loading";
import { ErrorState } from "@/components/states/States";
import { ApiRequestError } from "@/api/client";
import { describeError } from "@/lib/errors";
import { formatCount } from "@/lib/format";
import { useCapabilities } from "@/lib/queries";
import { useSaveSettings, useSettings } from "@/lib/settings";
import { reveal, isDesktop } from "@/lib/desktop";
import { notify } from "@/lib/toast";

/** contract.py Settings: max_parallel_runs is 1..8. */
const PARALLEL = [1, 2, 3, 4, 5, 6, 7, 8];

export default function SettingsScreen() {
  const settings = useSettings();
  const save = useSaveSettings();
  const caps = useCapabilities();
  const [draft, setDraft] = useState<Settings | null>(null);

  useEffect(() => {
    if (settings.data && draft === null) setDraft(settings.data);
  }, [settings.data, draft]);

  const dirty =
    draft !== null &&
    settings.data !== undefined &&
    (draft.max_parallel_runs !== settings.data.max_parallel_runs ||
      draft.confirm_delete !== settings.data.confirm_delete ||
      Boolean(draft.offline) !== Boolean(settings.data.offline) ||
      (draft.gromacs_path ?? null) !== (settings.data.gromacs_path ?? null));
  const serverError = save.error instanceof ApiRequestError ? save.error.error : null;

  const submit = () => {
    if (!draft || !settings.data) return;
    // The theme is whatever is stored now (it is saved the moment it is chosen).
    save.mutate(
      {
        ...settings.data,
        max_parallel_runs: draft.max_parallel_runs,
        confirm_delete: draft.confirm_delete,
        offline: Boolean(draft.offline),
        gromacs_path: draft.gromacs_path ?? null,
      },
      {
        onSuccess: (stored) => {
          setDraft(stored);
          notify("done", "Settings saved");
        },
      },
    );
  };

  useCommand(dirty ? { id: "settings.save", title: "Save settings", run: submit } : null);

  return (
    <Screen title="Settings" purpose="Theme, how many runs at once, offline mode, GROMACS, and where the workspace lives.">
      <Section title="Appearance">
        <div className="field">
          <span className="field-label" id="theme-label">
            Theme
          </span>
          <ThemeSwitch withText />
          <p className="field-hint">
            Light paper for daylight; dark ink surfaces for evening work. System follows the operating system. Applied at once.
          </p>
        </div>
      </Section>

      <Section title="Runs">
        {settings.isPending || draft === null ? (
          settings.isError ? (
            <ErrorState error={settings.error} />
          ) : (
            <Loading label="Reading the settings" />
          )
        ) : (
          <form
            className="settings-form"
            onSubmit={(e) => {
              e.preventDefault();
              submit();
            }}
          >
            <Field
              label="Runs at once"
              hint="How many runs work in parallel. Compose and stochastic simulation also take one engine lock, so two of them never run together whatever this says."
              error={fieldError(serverError, "max_parallel_runs")}
            >
              <Select
                value={String(draft.max_parallel_runs)}
                onChange={(e) => setDraft({ ...draft, max_parallel_runs: Number(e.target.value) })}
                className="settings-select num"
              >
                {PARALLEL.map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </Select>
            </Field>
            <Switch
              checked={draft.confirm_delete}
              onChange={(v) => setDraft({ ...draft, confirm_delete: v })}
              label="Ask before deleting a run"
              hint="Deleting moves the run's folder to the workspace's trash folder; files a run wrote into a folder of yours are never touched."
            />
            <Switch
              checked={Boolean(draft.offline)}
              onChange={(v) => setDraft({ ...draft, offline: v })}
              label="Offline mode"
              hint="Nothing contacts BRENDA, UniProt, the RCSB or NCBI. A run whose request needs the network is refused with that reason; a model without a subject, a local .cif file and a GROMACS setup without a subject still run."
            />
            <Field
              label="GROMACS"
              optional
              hint={
                caps.data?.gromacs.found
                  ? `Found now: ${caps.data.gromacs.path ?? "gmx"}${caps.data.gromacs.version ? `, ${caps.data.gromacs.version}` : ""}. Leave empty to look for gmx on the PATH and in the Homebrew folders.`
                  : "The absolute path of a gmx executable. Leave empty to look for gmx on the PATH and in the Homebrew folders."
              }
              error={fieldError(serverError, "gromacs_path")}
            >
              <TextInput
                mono
                value={draft.gromacs_path ?? ""}
                placeholder="/opt/homebrew/bin/gmx"
                spellCheck={false}
                autoComplete="off"
                onChange={(e) => setDraft({ ...draft, gromacs_path: e.target.value.trim() === "" ? null : e.target.value })}
              />
            </Field>
            {serverError && !serverError.field ? <ErrorState error={serverError} /> : null}
            {save.isError && !serverError ? <ErrorState error={save.error} /> : null}
            <FormActions>
              <button type="submit" className="btn btn-primary" disabled={!dirty || save.isPending}>
                {save.isPending ? "Saving" : "Save"}
              </button>
              {dirty ? (
                <button type="button" className="btn btn-quiet" onClick={() => setDraft(settings.data ?? null)}>
                  Discard changes
                </button>
              ) : null}
            </FormActions>
          </form>
        )}
      </Section>

      <Section title="Workspace">
        {caps.isPending ? (
          <Loading label="Asking the server" />
        ) : caps.isError ? (
          <ErrorState error={caps.error} />
        ) : (
          <dl className="dl">
            <dt>Folder</dt>
            <dd>
              <span className="font-mono">{caps.data.data_dir.path}</span>
              {isDesktop() ? (
                <>
                  {" "}
                  <button
                    type="button"
                    className="btn btn-sm btn-quiet"
                    onClick={() =>
                      void reveal(caps.data.data_dir.path).catch((e: unknown) =>
                        notify("failed", "Finder did not open", { description: describeError(e).message }),
                      )
                    }
                  >
                    Show in Finder
                  </button>
                </>
              ) : null}
            </dd>
            <dt>Writable</dt>
            <dd>{caps.data.data_dir.writable ? "yes" : (caps.data.data_dir.reason ?? "no")}</dd>
            <dt>Runs kept</dt>
            <dd className="font-mono">{formatCount(caps.data.data_dir.runs)}</dd>
            <dt>Change it</dt>
            <dd>
              Start the server with <code>caterva studio --data-dir PATH</code>.
            </dd>
          </dl>
        )}
      </Section>
    </Screen>
  );
}
