"""Bounded cursor preparation before dispatch (spec Parts IV and VII).

A cut can touch a few positions inside a large saved cursor tree. Copying that
entire tree before attempting a funded dispatch would hide unbounded work in
context preparation. ``CursorTransaction`` journals only addressed changes::

    pending = CursorTransaction(account['context_cursors'])
    view_account['context_cursors'] = pending
    cut = compile_cut(..., account=view_account)
    # Once the controller has secured the dispatch's funding and recording:
    pending.commit()

Discarding the transaction, or simply dropping it, leaves the original cursor
tree unchanged. Nested dictionaries are wrapped lazily and cache one child
transaction per addressed key. Commit traverses only locally written/deleted
keys and changed descendants; it never enumerates a saved cursor dictionary.

The cursor tree contains dictionaries and immutable scalar leaves. Mutable
non-dictionary leaves are explicitly unsupported, because returning a raw list
would silently defeat rollback. Newly assigned dictionaries are owned by the
caller until commit; do not mutate them externally during preparation. The
controller serializes the original plain dictionary after committing, never a
proxy. Only the root transaction may commit/discard. This is a sequential
in-memory staging mechanism, not a concurrent transaction or crash-replay log.

As with any MutableMapping, explicitly iterating this view can enumerate its
visible keys. Construction, point lookup, mutation, length, commit and discard
do not perform that enumeration.
"""

from collections.abc import MutableMapping
import math


_MISSING = object()


class CursorTransaction(MutableMapping):
    """Lazy dictionary overlay with root-owned commit and discard.

    Point operations are independent of the size of untouched cursor maps.
    The underlying dictionaries must form the controller's ordinary cursor
    tree and must not be independently mutated during a pending transaction.
    ``commit`` is idempotent; use after commit/discard otherwise raises instead
    of accidentally becoming a second, untracked preparation.
    """

    def __init__(self, base, *, _parent=None, _key=None):
        if not isinstance(base, dict):
            raise TypeError("CursorTransaction requires a plain cursor dictionary")
        self._base = base
        self._parent = _parent
        self._key = _key
        self._root = self if _parent is None else _parent._root
        self._status = "open"
        self._writes = {}
        self._deleted = set()
        self._children = {}
        self._dirty_children = {}

    def _check_open(self):
        if self._root._status != "open":
            raise RuntimeError(f"Cursor transaction is {self._root._status}")

    @staticmethod
    def _check_value(value):
        if isinstance(value, CursorTransaction):
            raise TypeError("A cursor proxy cannot be stored or serialized as cursor data")
        if isinstance(value, dict) or value is None or type(value) in (str, int, bool):
            return
        if type(value) is float and math.isfinite(value):
            return
        raise TypeError("Cursor values must be dictionaries or immutable JSON scalar leaves")

    def _changed(self):
        if self._parent is not None and self._parent._children.get(self._key) is self:
            self._parent._dirty_children[self._key] = self
            self._parent._changed()

    def __getitem__(self, key):
        self._check_open()
        if key in self._deleted:
            raise KeyError(key)
        value = self._writes[key] if key in self._writes else self._base[key]
        self._check_value(value)
        if isinstance(value, dict):
            child = self._children.get(key)
            if child is None:
                child = CursorTransaction(value, _parent=self, _key=key)
                self._children[key] = child
            return child
        return value

    def __setitem__(self, key, value):
        self._check_open()
        self._check_value(value)
        self._writes[key] = value
        self._deleted.discard(key)
        # An old returned child is detached: subsequent writes through it can
        # no longer resurrect or overwrite a replacement at this key.
        self._children.pop(key, None)
        self._dirty_children.pop(key, None)
        self._changed()

    def __delitem__(self, key):
        self._check_open()
        if key not in self:
            raise KeyError(key)
        self._writes.pop(key, None)
        self._deleted.add(key)
        self._children.pop(key, None)
        self._dirty_children.pop(key, None)
        self._changed()

    def __contains__(self, key):
        self._check_open()
        return key not in self._deleted and (key in self._writes or key in self._base)

    def __len__(self):
        self._check_open()
        removed = sum(key in self._base for key in self._deleted)
        added = sum(key not in self._base for key in self._writes)
        return len(self._base) - removed + added

    def __iter__(self):
        self._check_open()
        for key in self._base:
            if key not in self._deleted:
                yield key
        for key in self._writes:
            if key not in self._base:
                yield key

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def setdefault(self, key, default=None):
        self._check_open()
        if key not in self:
            self[key] = default
        return self[key]

    def pop(self, key, default=_MISSING):
        self._check_open()
        if key not in self:
            if default is _MISSING:
                raise KeyError(key)
            return default
        value = self[key]
        del self[key]
        return value

    def _apply(self):
        # These are transaction-local journals, not the underlying map.
        for key in self._deleted:
            if key in self._base:
                del self._base[key]
        for key, value in self._writes.items():
            self._base[key] = value
        for child in self._dirty_children.values():
            child._apply()

    def commit(self):
        """Apply only touched entries and return the original plain dictionary."""
        if self._parent is not None:
            raise RuntimeError("Only the root cursor transaction may commit")
        if self._status == "committed":
            return self._base
        self._check_open()
        self._apply()
        self._status = "committed"
        return self._base

    def discard(self):
        """Abandon every staged descendant mutation without touching saved data."""
        if self._parent is not None:
            raise RuntimeError("Only the root cursor transaction may discard")
        if self._status == "discarded":
            return
        self._check_open()
        self._status = "discarded"
        self._writes.clear()
        self._deleted.clear()
        self._children.clear()
        self._dirty_children.clear()
