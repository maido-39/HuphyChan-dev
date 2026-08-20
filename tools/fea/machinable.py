"""Machinability constraints for the shape optimiser - because these parts are CNC-milled.

The first optimiser removed whatever was least stressed. On a walking robot that is mostly
the INTERIOR, so it hollowed the links out - a shape only additive manufacturing can make.
For a milled part that answer is worthless: a cutter has to reach every gram it removes,
from outside, along a straight line, with a tool that has a finite radius.

Three constraints, all enforced on a voxel image of the part:

  1. ACCESSIBILITY   a cell may only be cut if some allowed tool axis has a clear straight
                     path from that cell to the outside, through cells that are already
                     cut or were never material. This is what makes the removal a POCKET
                     rather than a void, and it is checked against the CURRENT state each
                     iteration, so material becomes reachable as the pocket deepens -
                     exactly how real machining proceeds.
  2. TOOL RADIUS     the cut region must survive a morphological opening with a ball of the
                     cutter radius. A slot narrower than the tool cannot be produced, and a
                     sharp internal corner cannot either - the opening removes both.
  3. REACH           a pocket deeper than `max_depth_ratio` x its own width needs a long
                     slender tool and chatters; cells beyond that depth are refused.

Tool axes default to +-X, +-Y, +-Z: 3-axis milling in up to six setups, or a 5-axis machine
indexing to each face. Passing fewer axes models fewer setups and gives a stricter answer.

Nothing here knows about stress; it answers only "could a cutter have made this".

Usage (as a library):
    M = Machinability(cen, vol, axes='xyz', tool_r=3.0)
    ok = M.can_remove(active_ids, candidate_ids)
"""
import numpy as np
from scipy import ndimage


class Machinability:
    """Voxel model of the stock, and the rules a cutter obeys inside it."""

    def __init__(self, cen, vol, axes='xyz', tool_r=3.0, max_depth_ratio=4.0, voxel=None):
        cen = np.asarray(cen, float)
        assert len(cen) == len(vol), 'centroid / volume length mismatch'
        # a voxel about one element across keeps the image faithful without exploding
        self.h = float(voxel or max(2.0, np.median(np.cbrt(np.asarray(vol) * 6.0))))
        self.tool_r = float(tool_r)
        self.max_depth_ratio = float(max_depth_ratio)
        self.lo = cen.min(0) - 2 * self.h
        self.dims = np.maximum(
            np.ceil((cen.max(0) + 2 * self.h - self.lo) / self.h).astype(int), 3)
        self.ijk = np.floor((cen - self.lo) / self.h).astype(int)
        self.ijk = np.clip(self.ijk, 0, self.dims - 1)
        self.axes = []
        for a, ax in enumerate('xyz'):
            if ax in axes:
                self.axes += [(a, +1), (a, -1)]
        assert self.axes, f'no tool axes selected from {axes!r}'
        # the cutter as a ball in voxels; a radius under one voxel cannot be resolved
        r = max(1, int(round(self.tool_r / self.h)))
        g = np.arange(-r, r + 1)
        X, Y, Z = np.meshgrid(g, g, g, indexing='ij')
        self.ball = (X ** 2 + Y ** 2 + Z ** 2) <= r * r
        self.r_vox = r

    def _grid(self, ids_present):
        """Boolean image: True where material is still there."""
        g = np.zeros(self.dims, bool)
        p = self.ijk[np.asarray(list(ids_present), int)]
        g[p[:, 0], p[:, 1], p[:, 2]] = True
        return g

    def accessible(self, solid):
        """Cells a cutter can reach along at least one axis through empty space."""
        acc = np.zeros_like(solid)
        for a, sgn in self.axes:
            # walking inward from the face, a cell is reachable while nothing solid has
            # been met yet; the first solid cell IS reachable (it is the cut face), what
            # lies behind it is not
            blocked = np.cumsum(solid if sgn < 0 else np.flip(solid, a), axis=a)
            blocked = blocked if sgn < 0 else np.flip(blocked, a)
            reach = blocked <= 1
            acc |= reach
        return acc

    def depth_ok(self, solid):
        """Refuse cells deeper than max_depth_ratio x the local open width."""
        # distance from each empty cell to the nearest solid gives the local half-width;
        # distance from each solid cell to the nearest empty gives how buried it is
        d_in = ndimage.distance_transform_edt(solid) * self.h
        return d_in <= self.max_depth_ratio * self.tool_r

    def can_remove(self, active_ids, cand_ids):
        """Subset of cand_ids a cutter could actually take out of the current shape."""
        active_ids = np.asarray(list(active_ids), int)
        cand_ids = np.asarray(list(cand_ids), int)
        if not len(cand_ids):
            return set()
        solid = self._grid(active_ids)
        acc = self.accessible(solid)
        dep = self.depth_ok(solid)

        # provisional cut, then keep only what the tool could sweep: opening the CUT set
        cut = np.zeros_like(solid)
        p = self.ijk[cand_ids]
        cut[p[:, 0], p[:, 1], p[:, 2]] = True
        cut &= acc & dep
        if cut.any():
            # a slot the tool cannot enter disappears under erosion and never comes back
            opened = ndimage.binary_dilation(
                ndimage.binary_erosion(cut | ~solid, self.ball), self.ball) & solid
            cut &= opened
        keep = cut[p[:, 0], p[:, 1], p[:, 2]]
        return set(int(e) for e in cand_ids[keep])

    def report(self, active_ids):
        solid = self._grid(active_ids)
        acc = self.accessible(solid)
        n = int(solid.sum())
        return dict(voxel_mm=round(self.h, 2), tool_r_mm=self.tool_r,
                    axes=len(self.axes), solid_cells=n,
                    reachable_pct=round(100 * float((acc & solid).sum()) / max(n, 1), 1))
