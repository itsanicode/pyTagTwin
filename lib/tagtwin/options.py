# -*- coding: utf-8 -*-
"""User-facing settings, with sane defaults and config round-tripping."""

from __future__ import division

from tagtwin import signature


class MatchOptions(object):
    """Everything the matching engine and the replicator can be tuned with.

    Distances are in feet (Revit's internal unit): 0.02 ft is about 6 mm.
    """

    _FIELDS = (
        ('position_tolerance', 0.02),
        ('allow_mirror', True),
        ('allow_rotation', True),
        ('use_relaxed_levels', True),
        ('relaxed_tolerance_factor', 1.0),
        ('min_anchor_separation', 1.0),
        ('max_anchor_groups', 12),
        ('max_anchors_per_group', 6),
        ('max_hypotheses', 4000),
        ('score_sample_size', 200),
        ('finalist_count', 6),
        ('refine_iterations', 3),
        ('snap_angle_degrees', 90.0),
        ('snap_angle_tolerance', 0.5),
        ('size_quantum', 0.01),
        # replication
        ('offset_mode', 'auto'),          # auto | model | view
        ('adapt_to_view_scale', True),
        ('rehost_to_matched_point', True),
        ('skip_existing', True),
        ('tag_untagged_elements', True),
        ('layout_match_level', 'exact'),
        ('lock_3d_views', False),
        ('copy_tags', True),
        ('copy_dimensions', True),
        ('copy_text', True),
        ('copy_detail_lines', True),
        ('copy_regions', True),
        ('copy_symbols', True),
        ('copy_spot_dimensions', True),
    )

    def __init__(self, **kwargs):
        for name, default in self._FIELDS:
            setattr(self, name, kwargs.pop(name, default))
        if kwargs:
            raise TypeError('unknown option(s): {0}'.format(', '.join(sorted(kwargs))))

    @classmethod
    def field_names(cls):
        return [name for name, _ in cls._FIELDS]

    @classmethod
    def default_for(cls, name):
        for field, default in cls._FIELDS:
            if field == name:
                return default
        raise KeyError(name)

    @property
    def layout_level(self):
        """How alike two elements must be to share a tag position.

        Looser than element matching needs to be: the question is only "does
        this kind of element get its tag up and to the left", so the system and
        type usually carry it even when sizes differ.
        """
        return {'exact': signature.STRICT,
                'type+system': signature.MEDIUM,
                'type': signature.LOOSE}.get(self.layout_match_level,
                                             signature.MEDIUM)

    @property
    def levels(self):
        if self.use_relaxed_levels:
            return (signature.STRICT, signature.MEDIUM, signature.LOOSE)
        return (signature.STRICT,)

    def tolerance_for(self, level):
        if level == signature.STRICT:
            return self.position_tolerance
        return self.position_tolerance * max(1.0, self.relaxed_tolerance_factor)

    def to_dict(self):
        return dict((name, getattr(self, name)) for name, _ in self._FIELDS)

    @classmethod
    def from_dict(cls, data):
        """Build options from stored config, ignoring anything unknown."""
        known = set(name for name, _ in cls._FIELDS)
        clean = {}
        for key, value in (data or {}).items():
            if key in known:
                clean[key] = value
        return cls(**clean)

    def __repr__(self):
        return '<MatchOptions tol={0} mirror={1} rotation={2}>'.format(
            self.position_tolerance, self.allow_mirror, self.allow_rotation)
