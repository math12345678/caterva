/**
 * Job activity in the top bar: how many runs are working, and, one click
 * away, each with its current stage, a way to open it and a way to cancel
 * it. Runs that finished during this session stay listed below, with how
 * they ended, so a notification dismissed too quickly is not the only
 * record (History has every run).
 */
import * as Popover from "@radix-ui/react-popover";
import { Square } from "lucide-react";
import { Link } from "wouter";

import { MarkLoader } from "@/components/brand/MarkLoader";
import { elapsed } from "@/lib/format";
import { announcement, useJobs } from "@/lib/jobs";

import { RunStatusMark } from "./RunStatusMark";

export function JobActivity() {
  const { jobs, active, cancel, hrefFor } = useJobs();
  const count = active.length;
  return (
    <Popover.Root>
      <Popover.Trigger
        className="btn btn-sm btn-quiet job-trigger"
        aria-label={count ? `${count} run${count === 1 ? "" : "s"} working; show them` : "No runs working; show recent runs"}
        data-active={count ? "true" : undefined}
      >
        {count ? <MarkLoader size={14} /> : <RunStatusMark status="done" meaning={null} />}
        <span className="font-mono">{count ? `${count} working` : "idle"}</span>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content className="overlay popover job-popover" align="end" sideOffset={6} collisionPadding={12}>
          <p className="job-popover-title">Runs this session</p>
          {jobs.length === 0 ? (
            <p className="muted job-empty">
              Nothing has run since this page opened. Every past run is in <Link href="/history">History</Link>.
            </p>
          ) : (
            <ul className="job-list">
              {jobs.map((job) => {
                const live = job.status === "queued" || job.status === "running";
                const ended = live ? null : announcement(job);
                return (
                  <li key={job.id} className="job-item">
                    <RunStatusMark status={job.status} meaning={job.outcome?.meaning ?? null} />
                    <div className="job-text">
                      <Popover.Close asChild>
                        <Link href={hrefFor(job)} className="job-title">
                          {job.title}
                        </Link>
                      </Popover.Close>
                      <span className="job-sub">
                        {live
                          ? job.cancelling
                            ? "cancelling"
                            : (job.stage?.label ?? job.status)
                          : (ended?.description || ended?.title.split(":")[0] || job.status)}
                        <span className="font-mono"> · {elapsed(job.createdAt, job.finishedAt)}</span>
                      </span>
                    </div>
                    {live ? (
                      <button
                        type="button"
                        className="btn btn-sm btn-quiet btn-icon"
                        aria-label={`Cancel ${job.title}`}
                        disabled={job.cancelling}
                        onClick={() => void cancel(job.id)}
                      >
                        <Square size={11} aria-hidden="true" />
                      </button>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          )}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
