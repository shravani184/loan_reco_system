"""
Ranking metrics and the mandatory baselines (P10). Offline only.

THE RECOMMENDER IS A RANKER AND IS EVALUATED AS ONE. Accuracy is not a meaningful
metric for it and is not computed here (AGENTS.md section 6 rule 7).

Every metric is computed PER GROUP and then averaged over groups, because a customer
with 120 candidates must not outweigh one with 3. Groups too small to express an order
are excluded from metrics that need one, and the count of exclusions is reported.
"""

import numpy as np

RELEVANT_THRESHOLD = 2  # "a good option" — the same bar the calibrator targets


def _dcg(gains: np.ndarray) -> float:
    discounts = 1.0 / np.log2(np.arange(2, len(gains) + 2))
    return float(np.sum((2.0**gains - 1.0) * discounts))


def ndcg_at_k(labels: np.ndarray, scores: np.ndarray, k: int) -> float | None:
    """
    NDCG@k for one group. None when the group has no positive gain at all, since
    dividing by an ideal DCG of zero is undefined rather than perfect.
    """
    if len(labels) == 0:
        return None
    order = np.argsort(-scores, kind="stable")
    ranked = labels[order][:k]
    ideal = np.sort(labels)[::-1][:k]
    ideal_dcg = _dcg(ideal.astype(np.float64))
    if ideal_dcg <= 0.0:
        return None
    return _dcg(ranked.astype(np.float64)) / ideal_dcg


def precision_at_k(labels: np.ndarray, scores: np.ndarray, k: int) -> float | None:
    if len(labels) == 0:
        return None
    order = np.argsort(-scores, kind="stable")
    top = labels[order][:k]
    if len(top) == 0:
        return None
    return float(np.mean(top >= RELEVANT_THRESHOLD))


def recall_at_k(labels: np.ndarray, scores: np.ndarray, k: int) -> float | None:
    relevant = int(np.sum(labels >= RELEVANT_THRESHOLD))
    if relevant == 0:
        return None
    order = np.argsort(-scores, kind="stable")
    top = labels[order][:k]
    return float(np.sum(top >= RELEVANT_THRESHOLD) / relevant)


def average_precision_at_k(labels: np.ndarray, scores: np.ndarray, k: int) -> float | None:
    relevant = int(np.sum(labels >= RELEVANT_THRESHOLD))
    if relevant == 0:
        return None
    order = np.argsort(-scores, kind="stable")
    top = labels[order][:k]
    hits = 0
    total = 0.0
    for position, label in enumerate(top, start=1):
        if label >= RELEVANT_THRESHOLD:
            hits += 1
            total += hits / position
    return float(total / min(relevant, k))


def reciprocal_rank(labels: np.ndarray, scores: np.ndarray) -> float | None:
    relevant = int(np.sum(labels >= RELEVANT_THRESHOLD))
    if relevant == 0:
        return None
    order = np.argsort(-scores, kind="stable")
    for position, label in enumerate(labels[order], start=1):
        if label >= RELEVANT_THRESHOLD:
            return 1.0 / position
    return None


def kendall_tau(labels: np.ndarray, scores: np.ndarray) -> float | None:
    """
    Tau-b against the label order, over all pairs. Needs at least two candidates and
    at least one discriminating label pair.
    """
    n = len(labels)
    if n < 2:
        return None
    concordant = discordant = 0
    label_ties = score_ties = 0
    for i in range(n):
        for j in range(i + 1, n):
            label_delta = labels[i] - labels[j]
            score_delta = scores[i] - scores[j]
            if label_delta == 0 and score_delta == 0:
                continue
            if label_delta == 0:
                label_ties += 1
                continue
            if score_delta == 0:
                score_ties += 1
                continue
            if (label_delta > 0) == (score_delta > 0):
                concordant += 1
            else:
                discordant += 1
    denominator = np.sqrt(
        (concordant + discordant + label_ties) * (concordant + discordant + score_ties)
    )
    if denominator <= 0:
        return None
    return float((concordant - discordant) / denominator)


def evaluate_ranking(groups_labels, groups_scores) -> dict:
    """
    Average each metric over the groups where it is defined, and report how many
    groups contributed. A metric averaged over a different number of groups than its
    neighbour is not comparable without that count.
    """
    metrics = {
        "ndcg@1": [],
        "ndcg@3": [],
        "ndcg@5": [],
        "precision@1": [],
        "precision@3": [],
        "recall@5": [],
        "map@5": [],
        "mrr": [],
        "kendall_tau": [],
    }
    for labels, scores in zip(groups_labels, groups_scores):
        labels = np.asarray(labels)
        scores = np.asarray(scores, dtype=np.float64)
        for k in (1, 3, 5):
            value = ndcg_at_k(labels, scores, k)
            if value is not None:
                metrics[f"ndcg@{k}"].append(value)
        for k in (1, 3):
            value = precision_at_k(labels, scores, k)
            if value is not None:
                metrics[f"precision@{k}"].append(value)
        for name, value in (
            ("recall@5", recall_at_k(labels, scores, 5)),
            ("map@5", average_precision_at_k(labels, scores, 5)),
            ("mrr", reciprocal_rank(labels, scores)),
            ("kendall_tau", kendall_tau(labels, scores)),
        ):
            if value is not None:
                metrics[name].append(value)

    summary = {
        name: round(float(np.mean(values)), 4) if values else None
        for name, values in metrics.items()
    }
    summary["groups_scored"] = len(groups_labels)
    summary["groups_contributing_ndcg@5"] = len(metrics["ndcg@5"])
    return summary


# --------------------------------------------------------------------------
# The three mandatory baselines. Reported side by side with the model, ALWAYS,
# including when the model loses (AGENTS.md section 6 rule 7).
# --------------------------------------------------------------------------
def random_scores(group, rng: np.random.Generator) -> np.ndarray:
    """Chance. The floor any model must clear to be worth deploying."""
    return rng.random(len(group.candidates))


def cheapest_emi_scores(group) -> np.ndarray:
    """
    Cheapest monthly payment first. A crude but genuinely useful heuristic, and the
    one a customer would most plausibly apply themselves.
    """
    return np.asarray([-candidate.emi for candidate in group.candidates])


def diagnostic_utility_scores(group) -> np.ndarray:
    """
    The v1.0 deterministic utility ranking — the architecture this redesign replaced.

    THIS IS THE BASELINE THAT MATTERS. If the learned recommender cannot beat a
    hand-weighted formula on held-out groups, the ML-first redesign has not yet earned
    its place, and that result is published rather than buried.
    """
    from app.core.diagnostics import diagnostic_utility_score

    return np.asarray(
        [
            diagnostic_utility_score(
                group.context.financial,
                group.context.portfolio,
                candidate,
                group.risk_pd,
            )
            for candidate in group.candidates
        ]
    )
