import { useState, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Check, Copy } from "lucide-react";
import { openUrl } from "@tauri-apps/plugin-opener";

interface MarkdownProps {
  text: string;
  linkColor?: string;
}

function CodeBlock({ children }: { children: ReactNode }) {
  const [copied, setCopied] = useState(false);
  const code = typeof children === "string" ? children : String(children ?? "");

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code.replace(/\n$/, ""));
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // буфер обмена недоступен — молча игнорируем, это не критично
    }
  };

  return (
    <div className="relative my-1 overflow-hidden rounded-[var(--radius-sm)] border" style={{ borderColor: "var(--border)" }}>
      <button
        type="button"
        onClick={handleCopy}
        className="absolute right-2 top-2 flex h-6 w-6 items-center justify-center rounded"
        style={{ background: "var(--bg-elevated)", color: "var(--text-secondary)" }}
        title="Скопировать код"
      >
        {copied ? <Check size={13} /> : <Copy size={13} />}
      </button>
      <pre
        className="overflow-x-auto p-3 pr-10 text-[13px] leading-relaxed"
        style={{ background: "var(--bg-elevated)", fontFamily: "Consolas, Menlo, monospace" }}
      >
        <code>{children}</code>
      </pre>
    </div>
  );
}

/** Рендер markdown-ответов Scott: код-блоки, списки, ссылки (открываются в
 * системном браузере, а не уводят из окна приложения), таблицы, жирный/курсив. */
export function Markdown({ text, linkColor }: MarkdownProps) {
  return (
    <div className="markdown-content flex flex-col gap-2 text-[15px]">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => <p className="whitespace-pre-wrap">{children}</p>,
          a: ({ href, children }) => (
            <a
              href={href}
              style={{ color: linkColor, textDecoration: "underline", cursor: "pointer" }}
              onClick={(e) => {
                e.preventDefault();
                if (href) void openUrl(href);
              }}
            >
              {children}
            </a>
          ),
          code: ({ className, children }) => {
            const isBlock = /language-/.test(className ?? "");
            if (isBlock) return <CodeBlock>{children}</CodeBlock>;
            return (
              <code
                className="rounded px-1.5 py-0.5 text-[13px]"
                style={{ background: "var(--bg-elevated)", fontFamily: "Consolas, Menlo, monospace" }}
              >
                {children}
              </code>
            );
          },
          pre: ({ children }) => <>{children}</>,
          ul: ({ children }) => <ul className="list-disc pl-5">{children}</ul>,
          ol: ({ children }) => <ol className="list-decimal pl-5">{children}</ol>,
          li: ({ children }) => <li className="pl-0.5">{children}</li>,
          h1: ({ children }) => <h1 className="text-[19px] font-bold">{children}</h1>,
          h2: ({ children }) => <h2 className="text-[17px] font-bold">{children}</h2>,
          h3: ({ children }) => <h3 className="text-[16px] font-semibold">{children}</h3>,
          blockquote: ({ children }) => (
            <blockquote className="border-l-2 pl-3 opacity-80" style={{ borderColor: "var(--border)" }}>
              {children}
            </blockquote>
          ),
          table: ({ children }) => (
            <div className="overflow-x-auto">
              <table className="border-collapse text-[13px]">{children}</table>
            </div>
          ),
          th: ({ children }) => (
            <th className="border px-2 py-1 text-left font-semibold" style={{ borderColor: "var(--border)" }}>
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="border px-2 py-1" style={{ borderColor: "var(--border)" }}>
              {children}
            </td>
          ),
          hr: () => <hr style={{ borderColor: "var(--border)" }} />,
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}
