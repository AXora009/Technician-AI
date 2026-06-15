import ReactMarkdown from "react-markdown";
import rehypeRaw from "rehype-raw";

function dimCitations(text: string): string {
  return text.replace(/(\[#?\d+(?:,\s*#?\d+)*\])/g,
    '<span style="color:var(--color-muted-foreground);opacity:0.45;font-size:0.78em;vertical-align:super;font-family:monospace">$1</span>'
  );
}

export function Markdown({ children }: { children: string }) {
  return (
    <div className="prose prose-sm prose-invert max-w-none text-foreground leading-relaxed [&_h1]:text-lg [&_h2]:text-base [&_h3]:text-sm [&_h1]:font-mono [&_h2]:font-mono [&_h3]:font-mono [&_pre]:bg-muted [&_pre]:rounded-sm [&_pre]:p-3 [&_code]:text-primary [&_code]:text-xs [&_code]:font-mono [&_a]:text-primary [&_ul]:my-1 [&_ol]:my-1 [&_li]:my-0.5 [&_p]:my-1.5 [&_strong]:text-foreground [&_blockquote]:border-l-primary [&_blockquote]:text-muted-foreground">
      <ReactMarkdown rehypePlugins={[rehypeRaw]}>{dimCitations(children)}</ReactMarkdown>
    </div>
  );
}
