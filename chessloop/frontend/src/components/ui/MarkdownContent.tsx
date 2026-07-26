import { marked } from "marked";
import DOMPurify from "dompurify";

marked.setOptions({ breaks: true });

interface MarkdownContentProps {
  content: string;
  className?: string;
}

const proseClasses = [
  "text-sm leading-relaxed text-ink-300",
  "[&_h1]:text-lg [&_h1]:font-semibold [&_h1]:text-ink-100 [&_h1]:mt-3 [&_h1]:mb-1.5 [&_h1]:first:mt-0",
  "[&_h2]:text-base [&_h2]:font-semibold [&_h2]:text-ink-100 [&_h2]:mt-3 [&_h2]:mb-1.5 [&_h2]:first:mt-0",
  "[&_h3]:text-sm [&_h3]:font-semibold [&_h3]:text-ink-100 [&_h3]:mt-2 [&_h3]:mb-1 [&_h3]:first:mt-0",
  "[&_p]:my-2 [&_p]:first:mt-0 [&_p]:last:mb-0",
  "[&_a]:text-gold-400 [&_a]:underline [&_a]:hover:text-gold-300",
  "[&_strong]:text-ink-100 [&_strong]:font-semibold",
  "[&_ul]:list-disc [&_ul]:list-inside [&_ul]:my-2 [&_ul]:space-y-0.5",
  "[&_ol]:list-decimal [&_ol]:list-inside [&_ol]:my-2 [&_ol]:space-y-0.5",
  "[&_blockquote]:border-l-2 [&_blockquote]:border-ink-600 [&_blockquote]:pl-3 [&_blockquote]:my-2 [&_blockquote]:text-ink-400",
  "[&_code]:bg-ink-800 [&_code]:rounded [&_code]:px-1 [&_code]:py-0.5 [&_code]:text-xs [&_code]:font-mono",
  "[&_pre]:bg-ink-800 [&_pre]:rounded [&_pre]:p-3 [&_pre]:my-2 [&_pre]:overflow-x-auto [&_pre_code]:bg-transparent [&_pre_code]:p-0",
  "[&_img]:max-w-full [&_img]:rounded [&_img]:my-2",
  "[&_hr]:border-ink-700 [&_hr]:my-3",
].join(" ");

export function MarkdownContent({ content, className = "" }: MarkdownContentProps) {
  const html = DOMPurify.sanitize(marked.parse(content, { async: false }) as string);

  return (
    <div
      className={`${proseClasses} ${className}`}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
