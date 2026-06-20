#!/usr/bin/env python3
"""Sign Co-occurrence Network Analysis (v2 — corrected).

WHAT CHANGED FROM THE PREVIOUS VERSION AND WHY
------------------------------------------------
1. DAMAGE-PLACEHOLDER BUG: "000" (illegible/damaged sign) is now stripped
   before building the network. It was previously a node in the graph.
2. AMBIGUOUS-READING NOTATION ('/'): resolved to the first listed reading,
   as in the other scripts, instead of being split into two real signs.
3. PERFORMANCE/CORRECTNESS BUG: PMI computation previously recomputed each
   sign's marginal document frequency by re-scanning the entire corpus
   inside a doubly-nested loop over all sign pairs (O(V^2 * N)). Marginal
   document frequencies are now computed once.
4. STATISTICAL RIGOR: the previous version kept an edge if raw co-occurrence
   count >= 3 and PMI > 0, with no correction for the fact that hundreds of
   sign pairs are being tested simultaneously on a sparse corpus -- almost
   guaranteeing some pairs clear that bar by chance alone. Edges are now kept
   only if they pass a hypergeometric test (exact, given the true document
   frequencies and corpus size) with Benjamini-Hochberg FDR control across
   all candidate pairs.
5. GRAPH ALGORITHMS REWRITTEN ON NETWORKX rather than hand-rolled: PageRank,
   betweenness centrality (exact, not the previous unscaled/rescaled
   approximation), and Louvain community detection now use networkx's
   tested, peer-reviewed implementations instead of a custom Louvain pass
   with a hand-derived (and easy to get subtly wrong) modularity-gain term.
"""

from __future__ import annotations

import argparse
import csv
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

import networkx as nx
from scipy.stats import hypergeom


SIGN_CHUNK_RE = re.compile(r"\d{3,4}(?:/\d{3,4})*")
ILLEGIBLE = "000"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def latex_escape(value: object) -> str:
    text = "" if value is None else str(value)
    replacements = {"\\": "/", "_": r"\_", "%": r"\%", "&": r"\&", "#": r"\#", "$": r"\$", "{": r"\{", "}": r"\}"}
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def latex_table(rows: list[dict[str, object]], fields: list[str], widths: list[str] | None = None) -> str:
    spec = "".join(widths) if widths else "l" * len(fields)
    lines = [rf"\begin{{tabular}}{{{spec}}}", r"\toprule"]
    lines.append(" & ".join(rf"\textbf{{{latex_escape(field)}}}" for field in fields) + r" \\")
    lines.append(r"\midrule")
    for row in rows:
        lines.append(" & ".join(latex_escape(row.get(field, "")) for field in fields) + r" \\")
    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    return "\n".join(lines)


def parse_signs(text: str | None) -> list[str]:
    raw = (text or "").strip()
    tokens: list[str] = []
    for chunk in SIGN_CHUNK_RE.findall(raw):
        sign = chunk.split("/")[0]
        if sign != ILLEGIBLE:
            tokens.append(sign)
    return tokens


def benjamini_hochberg(p_values: list[float], alpha: float = 0.05) -> list[bool]:
    """Returns a boolean mask of which p-values survive BH FDR control at
    the given alpha, preserving the input order."""
    m = len(p_values)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: p_values[i])
    threshold_rank = 0
    for rank, idx in enumerate(order, start=1):
        if p_values[idx] <= (rank / m) * alpha:
            threshold_rank = rank
    cutoff = p_values[order[threshold_rank - 1]] if threshold_rank > 0 else -1.0
    return [p <= cutoff for p in p_values]


def cosine_sim(v1: dict[str, float], v2: dict[str, float]) -> float:
    dot = sum(v1.get(k, 0) * v2.get(k, 0) for k in set(v1) & set(v2))
    mag1 = math.sqrt(sum(x * x for x in v1.values()))
    mag2 = math.sqrt(sum(x * x for x in v2.values()))
    if mag1 == 0 or mag2 == 0:
        return 0.0
    return dot / (mag1 * mag2)


def analyze_network(texts: list[list[str]], out_dir: Path) -> None:
    n_docs = len(texts)
    doc_freq: Counter = Counter()
    cooc: Counter = Counter()  # frozenset/tuple pair -> co-occurrence doc count
    bigram_counts: Counter = Counter()  # directed adjacent-sign transitions

    for text in texts:
        unique_signs = sorted(set(text))
        for s in unique_signs:
            doc_freq[s] += 1
        for i in range(len(unique_signs)):
            for j in range(i + 1, len(unique_signs)):
                cooc[(unique_signs[i], unique_signs[j])] += 1
        for i in range(len(text) - 1):
            bigram_counts[(text[i], text[i + 1])] += 1

    # --- Hypergeometric significance test for each candidate co-occurrence edge ---
    # Under the null (independent random placement into documents, holding each
    # sign's document frequency fixed), the number of documents containing both
    # u and v follows Hypergeometric(N=n_docs, n=doc_freq[u], K=doc_freq[v]).
    candidate_pairs = [(u, v, c) for (u, v), c in cooc.items() if c >= 2]
    p_values = []
    for u, v, c in candidate_pairs:
        n_u, n_v = doc_freq[u], doc_freq[v]
        # P(X >= c) where X ~ Hypergeom(n_docs, n_u, n_v)
        p = hypergeom.sf(c - 1, n_docs, n_u, n_v)
        p_values.append(float(p))

    survives = benjamini_hochberg(p_values, alpha=0.05)

    filtered_edges = []  # (u, v, count, pmi, p_value)
    for (u, v, c), p_val, keep in zip(candidate_pairs, p_values, survives):
        if not keep:
            continue
        p_uv = c / n_docs
        p_u = doc_freq[u] / n_docs
        p_v = doc_freq[v] / n_docs
        pmi = math.log2(p_uv / (p_u * p_v)) if p_u > 0 and p_v > 0 and p_uv > 0 else 0.0
        if pmi > 0:
            filtered_edges.append((u, v, c, pmi, p_val))

    # --- Build graphs with networkx ---
    G = nx.Graph()
    for u, v, c, pmi, p_val in filtered_edges:
        G.add_edge(u, v, weight=pmi, cooc_count=c, p_value=p_val)

    nodes = list(G.nodes())
    N = len(nodes)

    DG = nx.DiGraph()
    for (u, v), c in bigram_counts.items():
        DG.add_edge(u, v, weight=c)

    pr = nx.pagerank(DG, alpha=0.85, weight="weight") if DG.number_of_nodes() else {}

    degree_cent = nx.degree_centrality(G) if N > 1 else {n: 0.0 for n in nodes}
    weighted_degree = {n: sum(d["weight"] for _, _, d in G.edges(n, data=True)) for n in nodes}

    # Exact betweenness centrality (networkx's Brandes algorithm). The graph
    # here is small enough (hundreds of nodes after FDR filtering) for exact
    # computation to be fast, so no need for the previous unscaled sampling
    # approximation.
    betweenness = nx.betweenness_centrality(G, weight=None, normalized=True) if N > 2 else {n: 0.0 for n in nodes}

    communities = {}
    if N > 0:
        try:
            comm_sets = nx.algorithms.community.louvain_communities(G, weight="weight", seed=20260619)
        except Exception:
            comm_sets = [set(nodes)]
        for i, members in enumerate(comm_sets):
            for m in members:
                communities[m] = f"C{i}"

    classes = {}
    try:
        for row in read_csv(out_dir / "phonetic_variable_map.csv"):
            classes[row["Sign"]] = row.get("FunctionalClass", "Unknown")
    except FileNotFoundError:
        pass

    # Bridge heuristic: high betweenness relative to degree centrality marks
    # a node connecting otherwise-separate clusters rather than one embedded
    # deep inside a single dense cluster.
    bridge_map = {}
    for u in nodes:
        b = betweenness.get(u, 0.0)
        d = degree_cent.get(u, 0.0)
        bridge_map[u] = (b / (d + 0.01) > 2.0) and b > 0.05

    comm_members = defaultdict(list)
    for u, c in communities.items():
        comm_members[c].append(u)

    comm_stats = []
    for c, members in comm_members.items():
        class_counts = Counter(classes.get(m, "Unknown") for m in members if classes.get(m, "Unknown") != "Unknown")
        total_known = sum(class_counts.values())
        alignment = class_counts.most_common(1)[0][1] / total_known if total_known > 0 else 0.0
        dom_class = class_counts.most_common(1)[0][0] if total_known > 0 else "Unlabeled"

        subgraph = G.subgraph(members)
        possible = len(members) * (len(members) - 1) / 2
        density = (subgraph.number_of_edges() / possible) if possible > 0 else 0.0

        top_s = sorted(members, key=lambda x: pr.get(x, 0), reverse=True)[:5]
        comm_stats.append({
            "CommunityID": c, "Size": len(members), "Members": "; ".join(sorted(members)[:10]),
            "TopSignsByPageRank": "; ".join(top_s), "InternalDensity": f"{density:.3f}",
            "DominantClass": dom_class, "AlignmentScore": f"{alignment:.3f}",
        })
    comm_stats.sort(key=lambda r: r["Size"], reverse=True)

    pmi_vectors: dict[str, dict[str, float]] = defaultdict(dict)
    for u, v, data in G.edges(data=True):
        pmi_vectors[u][v] = data["weight"]
        pmi_vectors[v][u] = data["weight"]

    sims = []
    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            u, v = nodes[i], nodes[j]
            if communities.get(u) != communities.get(v):
                sim = cosine_sim(pmi_vectors[u], pmi_vectors[v])
                if sim > 0.2:
                    sims.append({
                        "SignI": u, "SignJ": v, "CosineSim": f"{sim:.3f}",
                        "CommunityI": communities.get(u, ""), "CommunityJ": communities.get(v, ""),
                        "Note": "Similar co-occurrence partners despite different community -- candidate functional/allographic relation, not confirmed",
                    })
    sims.sort(key=lambda x: float(x["CosineSim"]), reverse=True)

    node_rows = [
        {
            "Sign": u, "DocFrequency": doc_freq[u], "Degree": G.degree(u),
            "WeightedDegree": f"{weighted_degree[u]:.3f}", "DegreeCentrality": f"{degree_cent.get(u,0):.3f}",
            "Betweenness": f"{betweenness.get(u, 0.0):.4f}", "PageRank": f"{pr.get(u, 0.0):.6f}",
            "Community": communities.get(u, ""), "FunctionalClass": classes.get(u, "Unknown"),
            "IsBridge": bridge_map.get(u, False),
        }
        for u in nodes
    ]
    node_rows.sort(key=lambda x: float(x["PageRank"]), reverse=True)

    edge_rows = [
        {
            "SignI": u, "SignJ": v, "CoocDocCount": c, "PMI": f"{p:.3f}", "HypergeomP": f"{pv:.2e}",
            "DirectedAdjacency": bigram_counts.get((u, v), 0) + bigram_counts.get((v, u), 0),
            "SameCommunity": communities.get(u) == communities.get(v),
        }
        for u, v, c, p, pv in filtered_edges
    ]
    edge_rows.sort(key=lambda x: float(x["PMI"]), reverse=True)

    if node_rows:
        write_csv(out_dir / "sign_network_nodes.csv", node_rows, list(node_rows[0].keys()))
    if edge_rows:
        write_csv(out_dir / "sign_network_edges.csv", edge_rows, list(edge_rows[0].keys()))
    if comm_stats:
        write_csv(out_dir / "sign_communities.csv", comm_stats, list(comm_stats[0].keys()))
    if sims:
        write_csv(out_dir / "sign_similarity_pairs.csv", sims[:50], list(sims[0].keys()))

    n_tested = len(candidate_pairs)
    n_survived_bh = sum(survives)
    summary = [
        {"Metric": "Documents (inscriptions) used", "Value": str(n_docs)},
        {"Metric": "Candidate sign-pairs tested (raw co-occurrence >= 2)", "Value": str(n_tested)},
        {"Metric": "Pairs surviving hypergeometric test + BH-FDR (alpha=0.05)", "Value": str(n_survived_bh)},
        {"Metric": "Edges retained after also requiring PMI > 0", "Value": str(len(filtered_edges))},
        {"Metric": "Network nodes (signs with >=1 retained edge)", "Value": str(N)},
        {"Metric": "Communities detected (Louvain)", "Value": str(len(comm_members))},
    ]
    write_csv(out_dir / "network_summary.csv", summary, ["Metric", "Value"])

    latex = r"""\section{Sign Co-occurrence Network Analysis}

Edges represent sign pairs that co-occur within the same inscription far more
often than chance would predict given each sign's overall frequency, tested
exactly via the hypergeometric distribution and controlled for multiple
testing across all candidate pairs with Benjamini-Hochberg FDR correction
(alpha = 0.05). Of """ + str(n_tested) + r""" candidate pairs, """ + str(n_survived_bh) + r""" survived
the significance test, and """ + str(len(filtered_edges)) + r""" of those also had positive PMI and were
retained as edges. PageRank, betweenness centrality, and community detection
(Louvain modularity) use the \texttt{networkx} library's tested
implementations rather than custom code, including correct handling of
dangling nodes in PageRank.

\subsection{Community Structure}
""" + (latex_table(comm_stats[:10], ["CommunityID", "Size", "TopSignsByPageRank", "DominantClass", "AlignmentScore"],
                    ["l", "r", "p{0.32\\textwidth}", "l", "r"]) if comm_stats else "No communities detected.") + r"""

\subsection*{Caveat}
A statistically significant co-occurrence edge shows two signs appear
together more than chance predicts; it does not by itself establish what
relationship (semantic, grammatical, or purely formulaic co-location) produces
that pattern. Community labels and the bridge-node heuristic are descriptive
groupings to guide further epigraphic inspection, not confirmed functional
classes.
"""
    (out_dir / "sign_cooccurrence_network.tex").write_text(latex, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default="data", help="Directory containing corpus")
    parser.add_argument("--outputs", default="outputs", help="Directory for outputs")
    args = parser.parse_args()

    data_dir = Path(args.data)
    out_dir = Path(args.outputs)
    out_dir.mkdir(parents=True, exist_ok=True)

    corpus_path = data_dir / "ivs_corpus_cleaned.csv"
    if not corpus_path.exists():
        print(f"Error: {corpus_path} not found.")
        return

    texts = []
    for row in read_csv(corpus_path):
        tokens = parse_signs(row.get("text", ""))
        if len(tokens) >= 2:
            texts.append(tokens)

    analyze_network(texts, out_dir)
    print("Sign co-occurrence network complete.")


if __name__ == "__main__":
    main()
