/**
 * Markdown renderer for memo bodies and TA debate panels.
 *
 * Wraps react-markdown with remark-gfm and overrides h1-h6 to render as
 * block headings with a consistent size (an <h5> equivalent), per the spec's
 * fix for the Jinja UI which inlined headings flush with body copy. Other
 * elements use the default tokens so we stay within the shadcn neutral palette.
 *
 * Plugins are restricted on purpose: GFM tables and lists are useful, raw
 * HTML and remark-math are not (analyst reports paste arbitrary markdown
 * that occasionally tries to embed scripts).
 */
import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';

import { cn } from '@/lib/utils';

interface MdProseProps {
  children: string;
  className?: string;
  /** Smaller variant for nested contexts (entity descriptions inside cards). */
  compact?: boolean;
}

const components: Components = {
  // All heading levels render as small block headings. Source documents
  // routinely emit a wall of `##` over and over; this normalises them.
  h1: ({ children }) => <h5 className="mt-4 mb-2 text-sm font-semibold tracking-tight">{children}</h5>,
  h2: ({ children }) => <h5 className="mt-4 mb-2 text-sm font-semibold tracking-tight">{children}</h5>,
  h3: ({ children }) => <h5 className="mt-3 mb-1.5 text-sm font-semibold tracking-tight">{children}</h5>,
  h4: ({ children }) => <h5 className="mt-3 mb-1.5 text-sm font-semibold tracking-tight">{children}</h5>,
  h5: ({ children }) => <h5 className="mt-3 mb-1.5 text-sm font-semibold tracking-tight">{children}</h5>,
  h6: ({ children }) => <h5 className="mt-3 mb-1.5 text-sm font-semibold tracking-tight">{children}</h5>,
  p: ({ children }) => <p className="my-2 leading-relaxed">{children}</p>,
  ul: ({ children }) => <ul className="my-2 list-disc space-y-1 pl-5">{children}</ul>,
  ol: ({ children }) => <ol className="my-2 list-decimal space-y-1 pl-5">{children}</ol>,
  li: ({ children }) => <li className="leading-relaxed">{children}</li>,
  strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
  em: ({ children }) => <em className="italic">{children}</em>,
  code: ({ children, className }) => (
    <code className={cn('rounded bg-muted px-1 py-0.5 font-mono text-[0.85em]', className)}>
      {children}
    </code>
  ),
  pre: ({ children }) => (
    <pre className="my-2 overflow-x-auto rounded-md bg-muted p-3 font-mono text-xs">
      {children}
    </pre>
  ),
  table: ({ children }) => (
    <div className="my-3 overflow-x-auto rounded-md border">
      <table className="w-full text-xs">{children}</table>
    </div>
  ),
  th: ({ children }) => <th className="border-b px-2 py-1 text-left font-medium">{children}</th>,
  td: ({ children }) => <td className="border-b px-2 py-1">{children}</td>,
  blockquote: ({ children }) => (
    <blockquote className="my-2 border-l-2 border-muted-foreground/30 pl-3 italic text-muted-foreground">
      {children}
    </blockquote>
  ),
  hr: () => <hr className="my-4 border-border" />,
  a: ({ children, href }) => (
    <a
      href={href}
      className="underline underline-offset-2 hover:text-foreground"
      rel="noreferrer noopener"
      target="_blank"
    >
      {children}
    </a>
  ),
};

export function MdProse({ children, className, compact }: MdProseProps) {
  return (
    <div
      className={cn(
        'text-sm text-foreground/85',
        compact && 'text-xs',
        className,
      )}
      data-testid="md-prose"
    >
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {children}
      </ReactMarkdown>
    </div>
  );
}
