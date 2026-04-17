# Scoring methodology

This document is the authoritative reference for the three embeddedness
dimensions, their raw and available-adjusted forms, and the composite
scores. Any change to the formulas here is a coordinated change: the
matching updates go to `src/repository_object_mapper/score.py`, the
test cases in `tests/test_score.py`, and the `CHANGELOG.md`.

## Principles

- **Three theoretically distinct dimensions.** Relational, agent, object.
  Each captures a different aspect of how the article record is embedded
  in the repository's documentary assemblage.
- **Raw and available-adjusted forms.** Raw measures what the record
  contains. Adjusted normalizes by what the repository's infrastructure
  permits. Both are reported; their divergence is the substantive finding.
- **Pooled min-max normalization for raw forms.** After the raw score is
  computed, it is rescaled to `[0, 1]` using the min and max observed in
  the pooled v0.2 corpus so that cross-repository comparison is
  well-defined. The adjusted forms are already ratios in `[0, 1]` and are
  not rescaled.
- **Explicit missingness.** Records whose source format does not expose a
  given field are handled distinctly from records where the field is
  exposed but unpopulated. The adjusted forms exploit this distinction.

## Notation

Let a record $r$ have:

- relation set $R_r$ with native types $T_r = \{t_1, \ldots\}$
- creator set $C_r$ with ORCID-bearing subset $C_r^{\text{orcid}}$
- affiliation set $A_r$ with ROR-bearing subset $A_r^{\text{ror}}$
- funder set $F_r$ with funder-id subset $F_r^{\text{id}}$ and project-id
  subset $F_r^{\text{proj}}$
- relations resolved under policy $\pi \in \{\text{fully}, \text{fully+weakly}\}$,
  yielding resolved set $R_r^\pi$ with distinct resolved types $S_r^\pi$

Let the repository $\rho(r)$ have capability profile entries:

- $T^{\text{avail}}_{\rho}$ = distinct native relation types seen in $\rho$'s
  corpus (used as a practical proxy for "available" — see the design note
  below)
- $I^{\text{slots}}_{\rho}$ = count of schema-exposed agent identifier
  slots from `describe_capabilities` (ORCID, ROR, funder id, project id)
- $K_\rho$ = infrastructure proxy for object embeddedness, taken as
  $|T^{\text{avail}}_{\rho}|$

## Dimensions

### 1. Relational embeddedness

**Raw.**

$$
\text{relational\_raw}(r) = \log(1 + |R_r|) + \frac{|T_r|}{c}
$$

with $c = 10$ (a fixed scaling constant that keeps the distinct-type
bonus on the same scale as the log-count term before pooled min-max
normalization).

**Adjusted.**

$$
\text{relational\_adjusted}(r) = \min\left(1, \; \frac{|T_r|}{|T^{\text{avail}}_{\rho}|}\right)
$$

with the convention that the adjusted score is $0$ when
$|T^{\text{avail}}_{\rho}| = 0$.

### 2. Agent embeddedness

**Raw.** Mean of four components, each in $[0, 1]$:

- $o_{\text{orcid}}(r) = |C_r^{\text{orcid}}| / |C_r|$ if $C_r \neq \emptyset$ else $0$
- $o_{\text{ror}}(r) = \mathbb{1}[A_r^{\text{ror}} \neq \emptyset]$
- $o_{\text{funder}}(r) = \mathbb{1}[F_r^{\text{id}} \neq \emptyset]$
- $o_{\text{project}}(r) = \mathbb{1}[F_r^{\text{proj}} \neq \emptyset]$

$$
\text{agent\_raw}(r) = \frac{1}{4} \sum_k o_k(r)
$$

**Adjusted.**

$$
\text{agent\_adjusted}(r) = \min\left(1, \; \frac{\text{observed\_identifier\_types}(r)}{I^{\text{slots}}_{\rho}}\right)
$$

where `observed_identifier_types(r)` is the count of the four components
that are strictly positive.

### 3. Object embeddedness

Computed once per resolution-inclusion policy $\pi$.

**Raw.**

$$
\text{object\_raw}^\pi(r) = \log(1 + |R_r^\pi|) + \frac{|S_r^\pi|}{c}
$$

**Adjusted.**

$$
\text{object\_adjusted}^\pi(r) = \min\left(1, \; \frac{|S_r^\pi|}{K_\rho}\right)
$$

The paper reports both $\pi = \text{fully}$ (primary) and
$\pi = \text{fully+weakly}$ (sensitivity). The latter is more permissive
but less certain; its divergence from the former is itself informative.

### Pooled normalization

After computing raw scores for all records in the pooled corpus, each raw
score is rescaled:

$$
x_{\text{norm}} = \frac{x - \min x}{\max x - \min x}
$$

with the convention $x_{\text{norm}} = 0$ when $\min x = \max x$.

### Composite

$$
\text{overall}(r) = \frac{\text{relational\_norm}(r) + \text{agent\_raw}(r) + \text{object\_norm}^{\text{fully}}(r)}{3}
$$

and

$$
\text{article\_autonomy\_score}(r) = 1 - \text{overall}(r)
$$

retained as a legacy convenience inverse; **not primary**.

## Worked examples

These examples correspond one-to-one with the hand-calculated expected
values in `tests/test_score.py`. If you change a formula here, you must
update both the function and the test.

### Example 1: a richly embedded article

- 2 relations, 2 distinct native types (`IsSupplementTo`, `IsVersionOf`)
- 1 creator with ORCID, 1 affiliation with ROR, 1 funder with id, 1 project
  id
- Resolved: the `IsSupplementTo` link is fully-typed (Dataset); the
  `IsVersionOf` link is weakly-typed (Preprint)

Relational raw (pre-normalization):
$\log(1+2) + 2/10 \approx 1.0986 + 0.2 = 1.2986$.

Agent raw: mean of `(1.0, 1.0, 1.0, 1.0) = 1.0`.

Object raw under `fully`:
$\log(1+1) + 1/10 \approx 0.6931 + 0.1 = 0.7931$.

Object raw under `fully+weakly`:
$\log(1+2) + 2/10 \approx 1.0986 + 0.2 = 1.2986$.

If the capability profile reports 4 available relation types for the
repository, the adjusted relational score is
$\min(1, 2/4) = 0.5$.

### Example 2: a bare article

- No relations, 1 creator without ORCID, no affiliations with ROR, no
  funder ids, no project ids.

Relational raw: $\log(1+0) + 0 = 0$.
Agent raw: mean of `(0, 0, 0, 0) = 0`.
Object raw (any policy): $0$.

Adjusted scores all `0` when the corresponding denominators are
positive — the record populates none of the available slots.

## Design note: available affordances

The v0.2 implementation uses the count of **distinct native relation
types observed** in a repository's corpus as the available affordances
denominator for the relational dimension. This is a practical choice: the
exhaustive set of *permissible* relation types in DataCite is enormous
and includes many types that no real repository uses, so dividing by the
full enumeration would make every repository's adjusted score nearly
zero and the signal uninformative.

The observed-types-as-denominator choice is documented rather than
hidden; a sensitivity analysis using the full DataCite-permissible set is
straightforward to add and is deferred to v0.5. In the v0.2 paper this
choice is stated explicitly and interpreted carefully: the adjusted
relational score measures how much of the *actually-used* relational
vocabulary in a repository a given article employs.
