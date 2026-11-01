/**
 * Settings, Updates: the installed version, when Caterva.app last asked for
 * a newer one, a Check now button, and two switches (check automatically,
 * include prereleases).
 *
 * All of it belongs to the macOS shell, which owns the updater
 * (macos/Sources/Updater.swift) and answers through the desktop bridge, so
 * the switches apply at once and are not part of the Save form below them.
 * In a plain browser there is no shell: the section says so and offers
 * nothing to press.
 */
import { useCallback, useEffect, useState } from "react";

import { Switch } from "@/components/forms/Field";
import { Section } from "@/components/screen/Screen";
import { checkForUpdates, isDesktop, setUpdateOptions, type UpdateStatus, updateStatus } from "@/lib/desktop";
import { describeError } from "@/lib/errors";
import { formatDateTime } from "@/lib/format";
import { notify } from "@/lib/toast";

type Loaded = UpdateStatus | null | undefined;

export function UpdatesSection() {
  const desktop = isDesktop();
  // undefined: not read yet. null: the shell did not answer.
  const [status, setStatus] = useState<Loaded>(desktop ? undefined : null);

  const read = useCallback(() => {
    if (!isDesktop()) return Promise.resolve();
    return updateStatus()
      .then(setStatus)
      .catch(() => setStatus(null));
  }, []);

  useEffect(() => {
    void read();
    // Sparkle's own window takes focus while it works; read again when it gives it back.
    window.addEventListener("focus", read);
    return () => window.removeEventListener("focus", read);
  }, [read]);

  const change = (options: { automatic?: boolean; prereleases?: boolean }) =>
    setUpdateOptions(options)
      .then(read)
      .catch((e: unknown) => notify("failed", "The update setting was not changed", { description: describeError(e).message }));

  const checkNow = () =>
    checkForUpdates()
      .then(() => {
        void read();
        // The check runs in the background; its time is recorded when it ends.
        window.setTimeout(() => void read(), 4000);
      })
      .catch((e: unknown) => notify("failed", "Caterva could not check for updates", { description: describeError(e).message }));

  return (
    <Section title="Updates">
      {!desktop ? (
        <p>Caterva.app updates itself. This page is open in a browser, not in the app, so there is nothing to set here.</p>
      ) : status === undefined ? (
        <p aria-live="polite">Asking the app</p>
      ) : status === null ? (
        <p>This copy of the app does not report its update settings.</p>
      ) : !status.enabled ? (
        <dl className="dl">
          <dt>Installed version</dt>
          <dd className="font-mono">{status.version}</dd>
          <dt>Updates</dt>
          <dd>{status.reason ?? "Off in this build."}</dd>
        </dl>
      ) : (
        <div className="settings-form">
          <dl className="dl">
            <dt>Installed version</dt>
            <dd className="font-mono">
              {status.version} (build {status.build})
            </dd>
            <dt>Last checked</dt>
            <dd>{status.lastCheck ? formatDateTime(status.lastCheck) : "never"}</dd>
          </dl>
          <div>
            <button type="button" className="btn btn-sm" disabled={status.checking} onClick={() => void checkNow()}>
              {status.checking ? "Checking" : "Check now"}
            </button>
          </div>
          <Switch
            checked={status.automatic}
            onChange={(v) => void change({ automatic: v })}
            label="Check automatically"
            hint="About once a day Caterva asks GitHub whether a newer release exists, and offers it; nothing is installed without your say. The request carries your address and the app's name and version, and nothing from your runs. This is separate from Offline mode."
          />
          <Switch
            checked={status.prereleases}
            onChange={(v) => void change({ prereleases: v })}
            label="Include prereleases"
            hint="Also offer release candidates, taken from the newest release on GitHub. They are tried less than a stable release. Turning this off does not go back to an earlier version."
          />
          {status.note ? <p className="field-hint">{status.note}</p> : null}
          <p className="field-hint">
            An update is checked against a key built into this app before it installs. That is not an Apple signature:
            Caterva is still not signed with an Apple Developer ID and not notarised. Installing closes Caterva; if a
            run is going, the app asks before it stops it. Your runs and settings stay in the workspace folder, and an
            update replaces only the app.
          </p>
        </div>
      )}
    </Section>
  );
}
