import unittest
import pymc as pm

from bn_testing.terms import (
    Linear,
    Monomial,
)


class TestCompositions(unittest.TestCase):

    def setUp(self):
        self.parents = ['x', 'y']
        self.t_a = Linear(self.parents, coefs=[1, 2])
        self.t_b = Linear(self.parents, coefs=[-1, -2])
        self.mapping = {'x': pm.math.constant(1), 'y': pm.math.constant(2)}

    def test_addition(self):
        a = self.t_a + self.t_b
        result = a.apply(self.mapping)
        self.assertEqual(result.eval(), 0)

    def test_multiplication_with_coefs(self):
        a = 3*self.t_a*self.t_b
        result = a.apply(self.mapping)
        self.assertEqual(result.eval(), 3*(1*1+2*2)*(-1*1-2*2))

    def test_left_right_multiplication(self):
        left = 4*self.t_a
        right = self.t_a*4
        self.assertEqual(
            left.apply(self.mapping).eval(),
            right.apply(self.mapping).eval(),
        )

    def test_powers(self):
        result = self.t_b**3
        self.assertEqual(
            result.apply(self.mapping).eval(),
            (-1*1-2*2)**3
        )


class TestMonomial(unittest.TestCase):

    def setUp(self):
        self.monomial = Monomial(
            parents=['x', 'y'],
            exponents=[1, 2])

        self.mapping = {'x': pm.math.constant(1), 'y': pm.math.constant(2)}

    def test_eval(self):
        self.assertEqual(
            self.monomial.apply(self.mapping).eval(),
            1**1*2**2
        )