"""Pure eligibility rules for explicitly filled, open planar shapes."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ShapeState:
    object_type: int
    closed: bool
    vertex_count: int
    fill_pattern: int
    fill_resource_type: int = 0
    locked: bool = False


def is_requested_fill(pattern, resource_type=0):
    # Appendix E: 1/2 = solid background/foreground; negative = resource.
    # Appendix D: hatch = 66. Gradients, images and tiles are not hatches.
    return pattern in (1, 2) or (pattern < 0 and resource_type == 66)


def candidate_reason(state):
    if state.object_type not in (5, 21):
        return "unsupported"
    if state.closed:
        return "closed"
    if not is_requested_fill(state.fill_pattern, state.fill_resource_type):
        return "unfilled"
    if state.vertex_count < 3:
        return "too_few_vertices"
    if state.locked:
        return "locked"
    return "eligible"
