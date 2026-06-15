import { useState } from "react";
import { ChevronRight, ChevronDown, GitBranch, Minus } from "lucide-react";
import type { Topic } from "@/types/api";

interface TreeNode {
  name: string;
  count: number;
  children: Map<string, TreeNode>;
}

function buildTree(topics: Topic[]): Map<string, TreeNode> {
  const root = new Map<string, TreeNode>();
  for (const t of topics) {
    const parts = Array.isArray(t.path) ? t.path : String(t.path).split(" > ");
    let level = root;
    for (let i = 0; i < parts.length; i++) {
      const name = parts[i];
      if (!level.has(name)) {
        level.set(name, { name, count: 0, children: new Map() });
      }
      const node = level.get(name)!;
      if (i === parts.length - 1) {
        node.count += (t.count ?? (t.manual_count ?? 0) + (t.knowledge_count ?? 0));
      }
      level = node.children;
    }
  }
  return root;
}

function sumCounts(node: TreeNode): number {
  let total = node.count;
  for (const child of node.children.values()) {
    total += sumCounts(child);
  }
  return total;
}

function TreeNodeItem({ node, depth }: { node: TreeNode; depth: number }) {
  const [open, setOpen] = useState(depth < 1);
  const hasChildren = node.children.size > 0;
  const total = sumCounts(node);

  return (
    <div>
      <button
        onClick={() => hasChildren && setOpen(!open)}
        className="flex items-center w-full gap-1 py-[3px] text-left hover:bg-accent/30 rounded-sm transition-colors"
        style={{ paddingLeft: `${depth * 14 + 2}px` }}
      >
        {hasChildren ? (
          open ? (
            <ChevronDown className="h-3 w-3 text-muted-foreground shrink-0" />
          ) : (
            <ChevronRight className="h-3 w-3 text-muted-foreground shrink-0" />
          )
        ) : (
          <span className="w-3 shrink-0" />
        )}
        {hasChildren ? (
          <GitBranch className="h-3 w-3 text-primary shrink-0" />
        ) : (
          <Minus className="h-2.5 w-2.5 text-muted-foreground shrink-0" />
        )}
        <span className="text-[11px] font-mono text-foreground/80 truncate flex-1 ml-0.5">
          {node.name}
        </span>
        <span className="text-[10px] font-mono text-muted-foreground tabular-nums pr-1">
          {total}
        </span>
      </button>
      {open && hasChildren && (
        <div>
          {[...node.children.values()].map((child) => (
            <TreeNodeItem key={child.name} node={child} depth={depth + 1} />
          ))}
        </div>
      )}
    </div>
  );
}

export function TopicTree({ topics }: { topics: Topic[] }) {
  const tree = buildTree(topics);

  if (!tree.size) {
    return (
      <p className="text-[11px] text-muted-foreground font-mono py-4 text-center">
        No topics yet. Upload a manual to get started.
      </p>
    );
  }

  return (
    <div>
      {[...tree.values()].map((node) => (
        <TreeNodeItem key={node.name} node={node} depth={0} />
      ))}
    </div>
  );
}
