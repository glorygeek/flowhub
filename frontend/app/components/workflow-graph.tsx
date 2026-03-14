import { WorkflowEdge, WorkflowNode } from "../lib/types";

export function WorkflowGraph({ nodes, edges }: { nodes: WorkflowNode[]; edges: WorkflowEdge[] }) {
  return (
    <div className="grid grid-2">
      <div>
        <h4>Nodes</h4>
        <ul>
          {nodes.map((node) => (
            <li key={node.id} className="small">
              <strong>{node.id}</strong> - {node.name} ({node.skill_ref || "n/a"})
            </li>
          ))}
        </ul>
      </div>
      <div>
        <h4>Edges</h4>
        <ul>
          {edges.map((edge) => (
            <li key={`${edge.from_node}:${edge.to_node}`} className="small">
              {edge.from_node} -&gt; {edge.to_node}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
