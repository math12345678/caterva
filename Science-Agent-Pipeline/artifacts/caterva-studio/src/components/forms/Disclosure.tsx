/**
 * A disclosure: detail that is there when wanted (a run's log, the
 * reproducing command, the advanced options of a form) and out of the way
 * otherwise. Progressive, in place, never a modal.
 */
import * as Collapsible from "@radix-ui/react-collapsible";
import { ChevronRight } from "lucide-react";
import type { ReactNode } from "react";

export function Disclosure({
  title,
  aside,
  children,
  defaultOpen = false,
  open,
  onOpenChange,
}: {
  title: ReactNode;
  /** A count or a short note beside the title, kept visible when closed. */
  aside?: ReactNode;
  children: ReactNode;
  defaultOpen?: boolean;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}) {
  return (
    <Collapsible.Root className="disclosure" defaultOpen={defaultOpen} open={open} onOpenChange={onOpenChange}>
      <Collapsible.Trigger className="disclosure-trigger">
        <ChevronRight size={14} aria-hidden="true" />
        <span>{title}</span>
        {aside ? <span className="disclosure-aside">{aside}</span> : null}
      </Collapsible.Trigger>
      <Collapsible.Content className="disclosure-content">
        <div className="disclosure-body">{children}</div>
      </Collapsible.Content>
    </Collapsible.Root>
  );
}
