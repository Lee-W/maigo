# Airflow design-integrity conventions (framework / base API design)

Loaded on demand by `skills/airflow-aware/SKILL.md` — design-level conventions
for framework-internal base classes, paired guard conditions, and
hot-loop extension surfaces (scheduler / triggerer / API request handler /
Dag parser). Read this file when designing or reviewing a new base/framework
API, a type-pairing guard, or an extension point on a hot loop.

Core ↔ SDK paired-class attribute symmetry is already covered in
`skills/airflow-aware/SKILL.md` §9 ("Core ↔ SDK paired-class symmetry") — not
repeated here.

---

## Type-pairing guards compare declared attributes, never "is method overridden" proxies

When guarding a constraint between two paired objects (e.g. two mapper
classes that must decode to the same type), compare a **declared attribute**
on both sides with a single equality check — do not use "is this method
overridden" as a proxy for the property you actually care about, and do not
write two directional/mirrored branches with duplicated messages.

Why: an override-based proxy encodes an assumption about *why* someone
overrides a method — an override can still return the same type, producing a
false rejection. A declared attribute states the contract directly, and a
symmetric mismatch check is one comparison (`if a.expected_type is not
b.expected_type: raise`), not two mirrored branches.

How to apply: when guarding a pairing constraint, add the declared-attribute
contract to **both** sides of the pair (core and SDK, if the pair spans
both), and write a single `is not` comparison. If one side already has the
declared attribute and the other doesn't, add it to the missing side rather
than working around the gap with an override check.

---

## Name a parameter's obvious counterpart symmetrically, not descriptively

When a class already has one half of an obvious pair as a parameter/field/
method name, name its counterpart symmetrically rather than reaching for a
role-descriptive label — prefer `upstream_mapper` / `downstream_mapper` over
`upstream_mapper` / `fine_mapper`. Symmetric naming makes the pairing
explicit at the call site and in docstrings.

This also applies **across sibling classes**, not just within one. If one
mapper class uses `upstream_mapper` / `downstream_mapper`, a structural
sibling class should use `upstream_mapper` for the same role — not a vague
near-synonym like `source_mapper`. Cross-class naming drift forces the
reader to learn two vocabularies for the same concept and obscures that the
classes are sibling compositions. Reach for descriptive names only when pair
members truly play different structural roles (e.g. `upstream_mapper` +
`window` is fine because they aren't the same kind of thing; `upstream_mapper`
+ `fine_mapper` is not, because both are mappers). Applies equally to method
names and attribute names, not just `__init__` kwargs — and the wire-format
(`serialize()`) shape follows the same renames.

---

## New extension surface on a scheduler/triggerer/API hot loop: two independent cost axes

Adding a user-extension surface to a framework hot loop (scheduler tick,
triggerer poll, API request handler, Dag parser callback) has **two
independent** scheduler-load dimensions — both must be answered, closing one
does not close the other:

1. **Per-call cost cap**: any user-overridable method on the extension point
   must be O(1) pure computation. A DB query, network call, unbounded loop,
   or file I/O on that path stalls the hot loop — including the framework's
   own builtin implementations, which must obey the same cap.
2. **Arbitrary user-logic risk**: even when every builtin implementation is
   O(1), an open (public, non-closed) extension surface lets a user subclass
   put arbitrary logic into it. The only reliable way to close this is a
   structural reject — an encoder/serializer `BUILTIN_*` allowlist plus a
   `<Foo>NotSupported`-style exception — not a loud disclaimer (see below).

How to apply: when evaluating a new callback / hook / policy object / event
filter / timetable extension on a hot path, answer both axes explicitly — (a)
is every builtin implementation genuinely O(1) (if not, don't expose it to
the hot loop, or cache/pre-compute); (b) does the subclass surface need
closing, and is the closing mechanism structural (see the next entry) rather
than a comment. Don't assume closing one axis buys safety on the other — a
closed subclass surface doesn't stop a builtin method from being slow, and a
fast builtin method doesn't stop a user subclass from adding an N+1 query.

---

## Close a framework-internal sum-type/policy object structurally, not visibly

A framework-internal sum-type / policy object (e.g. a small closed set of
builtin strategy classes consumed by a hot loop) should be **"low-key
closed"**, not hard-enforced with visible machinery. Structural close — an
encoder/serializer that rejects anything outside a `BUILTIN_*` allowlist — is
the actual enforcement. Visible signals like `abc.ABC` / `@abstractmethod` /
`__init_subclass__` raising / a `NotImplementedError` stub / an explicit "do
not subclass" disclaimer are all **loud "subclass me" signals** — they carry
the same IDE-autocomplete/`help()`/Sphinx visual weight as an invitation to
extend, whether the words say "subclass me" or "don't subclass me". A clean
user-facing interface (a plain base class, no methods, a docstring describing
only behavior) plus structural rejection at the encoder layer is more durable
than a text warning, especially for a hot-loop extension point (scheduler
tick / triggerer poll / API handler) where any DB query or network call a
user smuggles into an override degrades throughput.

How to apply when designing a new framework-internal sum-type / policy
object consumed by a hot path:

- Keep the user-facing (SDK-side) base a plain class with no methods; the
  docstring describes only observable behavior.
- If a type checker forces a method stub, keep the stub on the internal
  (core-only) side the user never imports.
- Reject non-builtin instances structurally at the encoder, via a
  `BUILTIN_*` allowlist plus a dedicated `NotSupported`-style exception.
- Don't write "extend / subclass to / extension point / pluggable" in the
  docstring — and don't write "do not subclass" either; both are the same
  kind of loud signal.
- Don't add `__init_subclass__`-style runtime hard-enforcement — it's heavier
  than the encoder-level reject and still advertises the extension point.
