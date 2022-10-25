import numpy as np
import pickle
import cloudpickle
import pandas as pd
import logging
import networkx as nx
import pymc as pm

from itertools import combinations
from abc import ABCMeta

from bn_testing.conditionals import ConstantConditional

logger = logging.getLogger(__name__)


class BayesianNetwork(metaclass=ABCMeta):
    """

    :param bn_testing.dags.DAG dag: A DAG generation method
    :param bn_testing.conditionals.Conditionals conditionals: A conditional type
    :param int random_state: A random state
    """

    def __init__(self, dag=None, conditionals=None, random_state=None):
        self.random_state = random_state
        self.random = np.random.RandomState(self.random_state)

        self.dag_gen = dag

        self.conditionals = conditionals
        self.conditionals.init(self.random)

        self.generate()
        self.n_nodes = self.dag.number_of_nodes

    def generate(self):
        """
        Generates the mod
        """
        logger.info('Generate DAG')
        self.dag = self.dag_gen.generate(random=self.random)
        logger.info('Generate models')
        self.terms = self._build_terms()
        self.sources = self._build_sources()
        self.noises = self._build_noises()

    @property
    def edges(self):
        return list(self.dag.edges())

    def modify_term(self, node, conditionals=None):

        if node not in self.nodes:
            raise ValueError(f'Unkown node {node}')

        if conditionals is None:
            conditionals = self.conditionals
        else:
            conditionals.init(self.random)
        self.terms[node] = conditionals.make_term(
            parents=self._get_parents(node),
            node=node
        )
        self.noises[node] = conditionals.make_noise()

    @property
    def nodes(self):
        return list(self.dag.nodes())

    @property
    def visible_nodes(self):
        return [n for n in self.nodes if not self.dag.nodes[n].get('is_hidden', False)]

    @property
    def hidden_nodes(self):
        return [n for n in self.nodes if self.dag.nodes[n].get('is_hidden', False)]

    def _get_parents(self, node):
        return [n for n, _ in self.dag.in_edges(node)]

    def is_source(self, node):
        """
        Checks if the given node is a source node, i.e., has no parents.

        Args:
            node (str): Name of a node in the dag

        Returns:
            bool: True if node is a source, false otherwise
        """
        return len(self._get_parents(node)) == 0

    def _build_noise(self, node):

        if self.dag.nodes[node].get('no_noise', False):
            return pm.math.constant(0)
        else:
            return self.dag.nodes[node].get(
                'noise',
                self.conditionals.make_noise()
            )

    def _build_noises(self):
        noises = {}
        for node in self.nodes:
            parents = self._get_parents(node)
            if len(parents) > 0:
                noises[node] = self._build_noise(node)
        return noises

    def _build_sources(self):
        """
        Builds PyMC variables that correspond to source nodes in the DAG.
        """
        sources = {}
        for node in self.nodes:
            if self.dag.in_degree(node) == 0:
                sources[node] = self.conditionals.make_source()
        return sources

    def _build_terms(self):
        terms = {}
        for node in self.nodes:
            parents = self._get_parents(node)
            if len(parents) > 0:
                terms[node] = self.dag.nodes[node].get(
                    'term',
                    # Check if dag has a term for that node, otherwise generate one using the
                    # conditional
                    self.conditionals.make_term(
                        parents=parents,
                        node=node,
                    )
                )
                assert set(terms[node].parents) == set(parents)
        return terms

    def _build_variable(self, node, parents_mapping):
        """
        Builds the variable corresponding to `node` by invoking the term created by the
        conditionals.

        :param str node: Name of the nodes
        :param dict parents_mapping: Mapping of node names to random variables.

        :returns: The build PyMC variable
        :rtype: pymc.distribution.Distribution

        """
        if len(parents_mapping.keys()) > 0:
            var = self.terms[node].apply(parents_mapping) + self.noises[node]
        else:
            # As generating the source introduces some randomness we would like to fix, we have to
            # build the source variables only once and reuse them here.
            var = self.sources[node]
        return var

    def compute_average_causal_effect(self, node_from=None, node_onto=None, value=None, n=1000):
        """
        Computes the average causal effect of a node that has a certain value onto another node.

        :param str node_from: Name of node that gets the intervention
        :param str node_onto: Variable whose change should be computed
        :param float value: Value of intervention
        :param int n: Sample size to approximate the expected values

        :returns: The average causal effect
        :rtype: float
        """
        df_orig = self.sample(n=n, nodes=[node_onto])

        if self.is_source(node_from):
            source = self.sources[node_from]
            term = ConstantConditional(value=value).make_term(
                parents=[],
                node=node_from
            )
            self.sources[node_from] = term.apply({})
        else:
            term = self.terms[node_from]
            noise = self.noises[node_from]

        self.modify_term(
            node=node_from,
            conditionals=ConstantConditional(value=value)
        )

        df_intervent = self.sample(n=n, nodes=[node_onto])

        if self.is_source(node_from):
            self.sources[node_from] = source
        else:
            self.terms[node_from] = term
            self.noises[node_from] = noise

        return df_intervent[node_onto].mean() - df_orig[node_onto].mean()

    def compute_varsortability(self, n=1000):
        """
        Computes the varsortability of the graphical model (see [Reisach et
        al.](https://arxiv.org/abs/2102.13647)), a number between 0 and 1 that measures how easy the
        graph structure can be read of the marginal variances (the larger, the easier).

        :param int n: The sample size to estimate the variances

        :returns: The varsortability of the dag
        :rtype: float
        """
        df = self.sample(n=n)

        var_order = df.var().sort_values(ascending=True).index

        n_all_increasing_paths = 0
        n_all_paths = 0

        for node_lower, node_higher in combinations(var_order, 2):
            n_increasing_paths = len(list(nx.all_simple_paths(
                G=self.dag,
                source=node_lower,
                target=node_higher,
            )))
            n_all_increasing_paths = n_all_increasing_paths + n_increasing_paths

            n_decreasing_paths = len(list(nx.all_simple_paths(
                G=self.dag,
                source=node_higher,
                target=node_lower,
            )))

            n_all_paths = n_all_paths + n_increasing_paths + n_decreasing_paths

        return n_all_increasing_paths / n_all_paths

    def _build_variables(self):
        variables = {}

        for node in nx.topological_sort(self.dag):
            parents_mapping = {
                parent: variables[parent] for parent, _ in self.dag.in_edges(node)
            }

            variables[node] = self._build_variable(node, parents_mapping)
        return variables

    def sample(self, n, nodes=None, normalize=False, exclude_hidden_nodes=True):
        """
        Samples `n` many identic and independent observations from the Bayesian network.

        :param int n: Number of observation to be created
        :param bool exclude_hidden_nodes: If :code:`True`, hidden nodes will be excluded. Defaults
            to :code:`True`.
        :param bool normalize: If true, each column in the resulting dataframe is divided by its
            standard deviation

        :returns: Dataframe in which the variables are columns and the observations are rows
        :rtype: pandas.DataFrame:
        """

        if nodes is None:
            nodes = self.nodes

        if exclude_hidden_nodes:
            nodes = [n for n in nodes if n not in self.hidden_nodes]
        else:
            logger.warning('Hidden nodes will be included in the result!')

        logger.info('Build variables')
        variables = self._build_variables()

        logger.info('Start sampling')
        data = pm.draw([variables[n] for n in nodes], draws=n, random_seed=self.random)
        df = pd.DataFrame(
            data=np.array(data).T,
            columns=nodes
        )

        if normalize:
            df = df/df.std()
        return df

    def show(self):
        """
        Visualizes the generated DAG.
        """
        self.dag_gen.show(self.dag)

    def save(self, filepath):
        """
        Saves the model to the specified file

        :param str filepath: Path to a file where model should be written to
        """

        model_pickled = cloudpickle.dumps(self)

        with open(filepath, 'wb') as f:
            pickle.dump(model_pickled, f)

    @staticmethod
    def load(filepath):
        """
        Loads the model from a file.

        :param str filepath: Path to a file where model has been written to with
            :py:func:`~bn_testing.models.BayesianNetwork.save`

        :returns: The loaded model
        :rtype: bn_testing.models.BayesianNetwork
        """

        with open(filepath, 'rb') as f:
            model_pickled = cloudpickle.loads(f.read())
        return pickle.loads(model_pickled)
