/**
 * The command's own report, exactly as the terminal prints it.
 *
 * Markdown (compose, cite) is rendered with markdown-it with raw HTML off,
 * so a report cannot inject markup; plain text (sim, bind) is shown as it
 * prints. Closed by default: the structured result above is the reading,
 * this is the document to check it against or to keep.
 */
import MarkdownIt from "markdown-it";
import { useMemo } from "react";

const markdown = new MarkdownIt({ html: false, linkify: false, typographer: false });

export function MarkdownBlock({ source }: { source: string }) {
  const html = useMemo(() => markdown.render(source), [source]);
  // markdown-it escapes every raw tag (html: false), so this is its output only.
  return <div className="k-markdown" dangerouslySetInnerHTML={{ __html: html }} />;
}

export function Report({
  title,
  markdown: source,
  text,
  open = false,
}: {
  title: string;
  markdown?: string;
  text?: string;
  open?: boolean;
}) {
  return (
    <details className="k-details k-section" open={open}>
      <summary>{title}</summary>
      {source !== undefined ? <MarkdownBlock source={source} /> : <pre className="k-pre">{text}</pre>}
    </details>
  );
}
