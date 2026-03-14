from collections import defaultdict, deque


def ensure_acyclic(node_ids: list[str], edges: list[tuple[str, str]]) -> list[str]:
    node_set = set(node_ids)
    indegree: dict[str, int] = {node_id: 0 for node_id in node_set}
    adjacency: dict[str, list[str]] = defaultdict(list)

    for from_node, to_node in edges:
        if from_node not in node_set or to_node not in node_set:
            raise ValueError(f"Edge references unknown node: {from_node} -> {to_node}")
        adjacency[from_node].append(to_node)
        indegree[to_node] += 1

    queue = deque([node for node, count in indegree.items() if count == 0])
    sorted_nodes: list[str] = []

    while queue:
        current = queue.popleft()
        sorted_nodes.append(current)
        for next_node in adjacency[current]:
            indegree[next_node] -= 1
            if indegree[next_node] == 0:
                queue.append(next_node)

    if len(sorted_nodes) != len(node_ids):
        raise ValueError("Graph contains a cycle.")
    return sorted_nodes
