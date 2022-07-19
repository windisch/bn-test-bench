"""
"""
import networkx as nx
import numpy as np
from itertools import combinations


def _group_iterator(groups):
    """
    Yields tuples of groups where the first element in the tuple can have influence on the second
    element in the tuple

    Args:
        groups (list): List of groups. Groups should be topologically sorted.
    Returns:
        iterable: Yields tuples of size two holding group names.
    """
    n = len(groups)
    for i in range(n):
        for j in range(i, n):
            yield groups[i], groups[j]


def compute_group_distance_matrix(model, dag_learned, distance_fn):
    """
    Computes the distances as specified in :code:`distance_fn` between the induced subgraphs of the
    groups among the true dag in :code:`model` and the :code:`dag_learned`.

    Args:
        model (bn_testing.dags.GroupedGaussianBN): The ground truth information
        dag_learned (nx.DiGraph): The infered dag structure.
        distance_fn (callable): A function with the arguments :code:`adj_truth` and :code:`adj_pred`
            for two adjacency matrices. Has to return a single score that represents the distance
            between the two graphs corresponding to the adjacency matrices.

    Returns:
        np.ndarray: A :py:cls:`np.ndarray` of shape :code:`(n_groups, n_groups)` where the
        :code:`(i,j)` entry represents the distance between the induced subgraphs of the true and
        predicted graph on the :code:`i`-th and :code:`j`-th groups.

    """

    distances = np.zeros((len(model.group_names), len(model.group_names)))

    for group_from, group_to in _group_iterator(model.group_names):

        dag_truth = model.get_grouped_subgraph([group_from, group_to])
        dag_pred = dag_learned.subgraph(dag_truth.nodes)

        distance = distance_fn(
            adj_truth=nx.to_numpy_matrix(dag_truth),
            adj_pred=nx.to_numpy_matrix(dag_pred),
        )

        distances[
            model.group_names.index(group_from),
            model.group_names.index(group_to)
        ] = distance
    return distances