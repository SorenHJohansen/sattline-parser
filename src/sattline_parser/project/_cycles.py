"""Elementary dependency-cycle enumeration.

A cycle is identified by its directed node sequence, not by its member set, so
``a -> b -> c -> a`` and ``a -> c -> b -> a`` stay distinct. Rotations of the
same sequence describe the same cycle, so canonicalisation rotates a sequence
to start at its smallest node name.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence


def cycle_key(cycle: Sequence[str]) -> tuple[str, ...]:
    """A rotation-invariant identity for one directed cycle.

    The optional closing repeat is stripped first, so ``("a", "b", "a")`` and
    ``("b", "a", "b")`` both become ``("a", "b")``. The direction is preserved:
    ``("a", "b", "c")`` and ``("a", "c", "b")`` are different keys.
    """
    nodes = tuple(cycle)
    if len(nodes) > 1 and nodes[0] == nodes[-1]:
        nodes = nodes[:-1]
    if not nodes:
        return ()
    return min(nodes[index:] + nodes[:index] for index in range(len(nodes)))


def canonical_cycle(cycle: Sequence[str]) -> tuple[str, ...]:
    """The closed form of ``cycle`` rotated to its canonical start."""
    key = cycle_key(cycle)
    return (*key, key[0]) if key else ()


def dependency_cycles(edges: Sequence[tuple[str, str]]) -> tuple[tuple[str, ...], ...]:
    """Every elementary dependency cycle, once, as a canonical closed path.

    Only strongly connected components can contain a cycle, so the search is
    confined to those. The result is sorted by canonical path, which makes it
    independent of edge insertion order.
    """
    adjacency: dict[str, list[str]] = {}
    for dependent, dependency in edges:
        adjacency.setdefault(dependent, []).append(dependency)

    found: dict[tuple[str, ...], tuple[str, ...]] = {}
    for component in _cyclic_components(adjacency):
        members = set(component)
        local = {node: [target for target in adjacency.get(node, ()) if target in members] for node in component}
        for start in component:
            _walk_cycles(start, local, found)
    return tuple(found[key] for key in sorted(found))


def _walk_cycles(
    start: str,
    adjacency: Mapping[str, Sequence[str]],
    found: dict[tuple[str, ...], tuple[str, ...]],
) -> None:
    """Enumerate every simple cycle through ``start`` inside its component."""
    trail = [start]
    iterators = [iter(adjacency.get(start, ()))]
    while iterators:
        try:
            neighbour = next(iterators[-1])
        except StopIteration:
            iterators.pop()
            trail.pop()
            continue
        if neighbour in trail:
            cycle = trail[trail.index(neighbour) :]
            key = cycle_key(cycle)
            if key not in found:
                found[key] = (*key, key[0])
            continue
        trail.append(neighbour)
        iterators.append(iter(adjacency.get(neighbour, ())))


def _strongly_connected_components(adjacency: Mapping[str, Sequence[str]]) -> list[list[str]]:
    """Tarjan's algorithm, iterative so a deep graph cannot exhaust the stack."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    components: list[list[str]] = []
    counter = 0
    nodes = sorted({*adjacency, *(target for targets in adjacency.values() for target in targets)})
    for root in nodes:
        if root in index:
            continue
        work: list[tuple[str, int]] = [(root, 0)]
        while work:
            node, position = work[-1]
            if position == 0:
                index[node] = counter
                low[node] = counter
                counter += 1
                stack.append(node)
                on_stack.add(node)
            targets = adjacency.get(node, ())
            if position < len(targets):
                work[-1] = (node, position + 1)
                neighbour = targets[position]
                if neighbour not in index:
                    work.append((neighbour, 0))
                elif neighbour in on_stack:
                    low[node] = min(low[node], index[neighbour])
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index[node]:
                component: list[str] = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    component.append(member)
                    if member == node:
                        break
                components.append(component)
    return components


def _cyclic_components(adjacency: Mapping[str, Sequence[str]]) -> list[list[str]]:
    """The components that hold a cycle, members sorted, in a stable order."""
    cyclic: list[list[str]] = []
    for component in _strongly_connected_components(adjacency):
        if len(component) > 1:
            cyclic.append(sorted(component))
        elif component[0] in adjacency.get(component[0], ()):
            cyclic.append(component)
    return sorted(cyclic)
