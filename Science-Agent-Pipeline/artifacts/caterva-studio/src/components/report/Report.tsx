/**
 * The command's own document: the Markdown `caterva compose` or `caterva
 * prepare` prints (`report_markdown`), or the plain text another command
 * prints (`report_text`), shown as "the same document the terminal
 * prints" (docs/studio/CONTRACT.md 13).
 *
 * Markdown is rendered with raw HTML disabled, so a string from a database
 * row that happens to contain markup is shown as text, never run; links
 * keep markdown-it's own refusal of javascript: and data: URLs and open
 * outside the app. Plain text keeps its columns in DM Mono.
 */
import MarkdownIt from "markdown-it";
import { useMemo } from "react";

import { cn } from "@/lib/cn";
import { plainMarkdown } from "@/lib/copy";

const md = new MarkdownIt({ html: false, linkify: true, typographer: false, breaks: false });

const defaultLink =
  md.renderer.rules.link_open ?? ((tokens, idx, options, _env, self) => self.renderToken(tokens, idx, options));
md.renderer.rules.link_open = (tokens, idx, options, env, self) => {
  tokens[idx].attrSet("target", "_blank");
  tokens[idx].attrSet("rel", "noopener noreferrer");
  return defaultLink(tokens, idx, options, env, self);
};

export function renderMarkdown(source: string): string {
  return md.render(source);
}

/**
 * `prose` rewrites the document's sentences (flags, dashes, plurals) for the
 * window and leaves code untouched; without it the document is exactly what
 * the terminal prints.
 */
export function MarkdownReport({ source, className, prose = false }: { source: string; className?: string; prose?: boolean }) {
  const html = useMemo(() => renderMarkdown(prose ? plainMarkdown(source) : source), [source, prose]);
  return <div className={cn("report", className)} dangerouslySetInnerHTML={{ __html: html }} />;
}

export function TextReport({ text, className }: { text: string; className?: string }) {
  return <pre className={cn("report-text", className)}>{text}</pre>;
}

/** A command line in an ink slab, with a copy button: how to reproduce a run in a terminal. */
export function CommandSlab({ argv, title = "In a terminal" }: { argv: readonly string[]; title?: string }) {
  const line = argv.map(shellQuote).join(" ");
  return (
    <div className="slab">
      <div className="slab-head">
        <span className="slab-dots" aria-hidden="true">
          <i />
          <i />
          <i />
        </span>
        <span>{title}</span>
        <button
          type="button"
          className="btn btn-sm slab-copy"
          onClick={() => void navigator.clipboard?.writeText(line)}
          aria-label="Copy the command"
        >
          Copy
        </button>
      </div>
      <div className="slab-body wrap">
        <span className="slab-prompt">$ </span>
        {line}
      </div>
    </div>
  );
}

/** POSIX shell quoting, the same rule as Python's shlex.quote, which writes command.txt in a bundle. */
export function shellQuote(arg: string): string {
  if (arg === "") return "''";
  if (/^[\w@%+=:,./-]+$/.test(arg)) return arg;
  return `'${arg.replace(/'/g, `'"'"'`)}'`;
}
