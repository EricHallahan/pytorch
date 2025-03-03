# Owner(s): ["module: dynamo"]
import operator
from typing import Dict, List
from unittest.mock import patch

import torch

import torch._dynamo.test_case
import torch._dynamo.testing
from functorch.experimental.control_flow import cond
from torch.fx.experimental.proxy_tensor import make_fx


class ExportTests(torch._dynamo.test_case.TestCase):
    # TODO(voz): Refactor to a shared test function.
    # The tests in this file are a little redundant,
    # They all take a func, run it with eager, then export it, then compare
    def test_export(self):
        def pre_attention_state_ops(input, mems, state):
            lc_key = state[0]
            lc_val = state[1]
            bar = []
            for i in range(0, 4):
                bar2 = []
                for j in range(0, 3):
                    bar2.append(
                        lc_key + lc_val + torch.tensor([0.1, 0.25, 0.4, 0.5, 0.1])
                    )
                bar.append(bar2)

            return bar

        def func():
            mems = torch.tensor([[[1.8364, 0.2724, -1.4917, -0.4367, 0.8640]]])
            state = [
                torch.tensor([[[1.0517, 0.3848, -0.6472, 0.0823, 0.9116]]]),
                torch.tensor([[[1.0517, 0.3848, -0.6472, 0.0823, 0.9116]]]),
            ]
            i = torch.tensor(
                [
                    [0.0313, -0.1487, -0.3846, -0.5321],
                    [-1.7073, 1.3331, -0.0890, -1.4935],
                    [-0.8314, -0.1862, -0.5935, 1.5232],
                ]
            )
            return pre_attention_state_ops(i, mems, state)

        opt_func = torch._dynamo.optimize("eager", nopython=True)(func)
        real_result = opt_func()

        torch._dynamo.reset()

        exported = torch._dynamo.export(func)
        out_graph = exported[0]

        dynamo_result = out_graph()
        self.assertTrue(torch._dynamo.utils.same(real_result, dynamo_result))

    def test_export_mismatched_out(self):
        def func(x):
            y = x + 1
            return ([x, x], (y, y))

        opt_func = torch._dynamo.optimize("eager", nopython=True)(func)
        real_result = opt_func(torch.tensor([[[1.3737, 0.1]]]))

        torch._dynamo.reset()

        exported = torch._dynamo.export(func, torch.tensor([[[1.3737, 0.1]]]))
        out_graph = exported[0]

        dynamo_result = out_graph(torch.tensor([[[1.3737, 0.1]]]))

        self.assertTrue(torch._dynamo.utils.same(real_result, dynamo_result))

    @patch.object(torch._dynamo.config, "dynamic_shapes", True)
    def test_export_shape_control_flow_1(self):
        def func(x):
            if x.shape[0] > 10:
                return x.cos()
            return x.sin()

        opt_func = torch._dynamo.optimize("eager")(func)
        real_result = opt_func(torch.ones(6, 4))

        torch._dynamo.reset()

        exported = torch._dynamo.export(func, torch.ones(6, 4))
        out_graph, out_guards = exported

        dynamo_result = out_graph(torch.ones(6, 4))

        from torch._guards import GuardSource

        self.assertTrue(torch._dynamo.utils.same(real_result, dynamo_result))
        hit = False
        for guard in out_guards:
            if guard.source == GuardSource.SHAPE_ENV:
                hit = True
                self.assertTrue("x.size()[0] <= 10" in guard.code_list[0])

        self.assertTrue(hit)

    def test_export_graph_bypass(self):
        inp = [
            torch.tensor([0.1, 0.1]),
            torch.tensor([0.2, 0.2]),
            torch.tensor([0.3, 0.3]),
        ]

        def func(x):
            first = x[2]
            second = x[2]
            return first * second

        opt_func = torch._dynamo.optimize("eager", nopython=True)(func)
        real_result = opt_func(inp)

        torch._dynamo.reset()

        exported = torch._dynamo.export(func, inp)
        out_graph = exported[0]

        dynamo_result = out_graph(inp)

        self.assertTrue(torch._dynamo.utils.same(real_result, dynamo_result))

    def test_list_unpack(self):
        inp = [
            torch.tensor([0.1, 0.1]),
            torch.tensor([0.2, 0.2]),
            torch.tensor([0.3, 0.3]),
        ]

        def func(x):
            first = x[2]
            second = x[2]
            return x[0], first * second, x[1], x[2]

        opt_func = torch._dynamo.optimize("eager", nopython=True)(func)
        real_result = opt_func(inp)

        torch._dynamo.reset()

        exported = torch._dynamo.export(func, inp)
        out_graph = exported[0]

        dynamo_result = out_graph(inp)

        self.assertTrue(torch._dynamo.utils.same(real_result, dynamo_result))

    def test_export_mismatched_out_2(self):
        def func(x):
            y = x + 1
            return ([x, x], (y, y))

        opt_func = torch._dynamo.optimize("eager", nopython=True)(func)
        real_result = opt_func(torch.tensor([[[1.3737, 0.1]]]))

        torch._dynamo.reset()

        exported = torch._dynamo.export(func, torch.tensor([[[1.3737, 0.1]]]))
        out_graph = exported[0]

        dynamo_result = out_graph(torch.tensor([[[1.3737, 0.1]]]))

        self.assertTrue(torch._dynamo.utils.same(real_result, dynamo_result))

    def test_export_graph_with_list(self):
        inp = [
            torch.tensor([0.1, 0.1]),
            torch.tensor([0.2, 0.2]),
            torch.tensor([0.3, 0.3]),
            torch.tensor([0.4, 0.4]),
        ]

        def func(x):
            first = x[2]
            second = x[2]
            return first * second, x

        opt_func = torch._dynamo.optimize("eager", nopython=True)(func)
        real_result = opt_func(inp)

        torch._dynamo.reset()

        exported = torch._dynamo.export(func, inp)
        out_graph = exported[0]

        dynamo_result = out_graph(inp)

        self.assertTrue(torch._dynamo.utils.same(real_result, dynamo_result))

    def test_export_graph_with_complex_reorder(self):
        inp = [
            torch.tensor([0.1, 0.1]),
            torch.tensor([0.2, 0.2]),
            torch.tensor([0.3, 0.3]),
            torch.tensor([0.4, 0.4]),
        ]

        def func(x):
            first = x[0]
            second = x[1]
            third = x[2]
            return third, first, second, first * second, first * third

        opt_func = torch._dynamo.optimize("eager", nopython=True)(func)
        real_result = opt_func(inp)

        torch._dynamo.reset()

        exported = torch._dynamo.export(func, inp)
        out_graph = exported[0]

        dynamo_result = out_graph(inp)

        self.assertTrue(torch._dynamo.utils.same(real_result, dynamo_result))

    def test_dupes(self):
        inp = torch.tensor([0.1, 0.1])

        def func(x):
            y = x + 1
            return y, y

        opt_func = torch._dynamo.optimize("eager", nopython=True)(func)
        real_result = opt_func(inp)

        torch._dynamo.reset()

        exported = torch._dynamo.export(func, inp)
        out_graph = exported[0]

        dynamo_result = out_graph(inp)

        self.assertTrue(torch._dynamo.utils.same(real_result, dynamo_result))

    def test_dupes_2(self):
        inp = torch.tensor([0.1, 0.1])

        def func(x):
            y = x + 1
            return y, y

        opt_func = torch._dynamo.optimize("eager", nopython=True)(func)
        real_result = opt_func(inp)

        torch._dynamo.reset()

        exported = torch._dynamo.export(func, inp)
        out_graph = exported[0]

        dynamo_result = out_graph(inp)

        self.assertTrue(torch._dynamo.utils.same(real_result, dynamo_result))

    def test_dupes_and_bypass(self):
        inp = torch.tensor([0.1, 0.1])
        inp2 = torch.tensor([0.4, 0.4])
        inps = [inp, inp2]

        def func(x, z):
            y = x + 1
            return y, y, z

        opt_func = torch._dynamo.optimize("eager", nopython=True)(func)
        real_result = opt_func(*inps)

        torch._dynamo.reset()

        exported = torch._dynamo.export(func, *inps)
        out_graph = exported[0]

        dynamo_result = out_graph(*inps)

        self.assertTrue(torch._dynamo.utils.same(real_result, dynamo_result))

    def test_dupes_and_bypass_with_non_tensor_arg(self):
        inp = torch.tensor([0.1, 0.1])
        inp2 = torch.tensor([0.1, 0.1])
        inp3 = 4
        inps = [inp, inp2, inp3]

        def func(x, z, k):
            y = x + k
            return y, y, z

        opt_func = torch._dynamo.optimize("eager", nopython=True)(func)
        real_result = opt_func(*inps)

        torch._dynamo.reset()

        exported = torch._dynamo.export(func, *inps)
        out_graph = exported[0]

        dynamo_result = out_graph(*inps)

        self.assertTrue(torch._dynamo.utils.same(real_result, dynamo_result))

    def test_dupes_and_bypass_reorder_with_non_tensor_arg(self):
        inp = torch.tensor([0.1, 0.1])
        inp2 = torch.tensor([0.1, 0.1])
        inp3 = 4
        inps = [inp, inp2, inp3]

        def func(x, z, k):
            y = x + k
            return z, y, y

        opt_func = torch._dynamo.optimize("eager", nopython=True)(func)
        real_result = opt_func(*inps)

        torch._dynamo.reset()

        exported = torch._dynamo.export(func, *inps)
        out_graph = exported[0]

        dynamo_result = out_graph(*inps)

        self.assertTrue(torch._dynamo.utils.same(real_result, dynamo_result))

    @patch.object(torch._dynamo.config, "capture_scalar_outputs", True)
    def test_dupes_and_bypass_with_non_tensor_output(self):
        inp = torch.tensor([0.1, 0.1])
        inp2 = torch.tensor([0.1, 0.1])
        inp3 = 4
        inps = [inp, inp2, inp3]

        def func(x, z, k):
            y = x + k
            return y[0].item(), y, z

        opt_func = torch._dynamo.optimize("eager", nopython=True)(func)
        real_result = opt_func(*inps)

        torch._dynamo.reset()

        exported = torch._dynamo.export(func, *inps)
        out_graph = exported[0]

        dynamo_result = out_graph(*inps)

        self.assertTrue(torch._dynamo.utils.same(real_result, dynamo_result))

    def test_zeroes_in_and_out_different_shape_on_test(self):
        inp = torch.zeros(10)
        inp2 = torch.zeros(10)
        inp3 = torch.zeros(10)
        inps = [inp, inp2, inp3]

        inps_rand = [torch.randn(10), torch.randn(10), torch.randn(10)]

        def func(a, b, c):
            return [[a], [b, c], [a + b], [[c + c]]]

        opt_func = torch._dynamo.optimize("eager", nopython=True)(func)
        real_result = opt_func(*inps_rand)

        torch._dynamo.reset()

        exported = torch._dynamo.export(func, *inps)
        out_graph = exported[0]

        dynamo_result = out_graph(*inps_rand)

        self.assertTrue(torch._dynamo.utils.same(real_result, dynamo_result))

    @patch.object(torch._dynamo.config, "capture_scalar_outputs", True)
    def test_zeroes_in_new_shape_scalar_out(self):
        inp = torch.zeros(10)
        inp2 = torch.zeros(10)
        inp3 = torch.zeros(10)
        inps = [inp, inp2, inp3]

        inps_rand = [torch.randn(10), torch.randn(10), torch.randn(10)]

        def func(a, b, c):
            return a[0].item() + b[0].item() + c[0].item()

        opt_func = torch._dynamo.optimize("eager", nopython=True)(func)
        real_result = opt_func(*inps_rand)

        torch._dynamo.reset()

        exported = torch._dynamo.export(func, *inps)
        out_graph = exported[0]

        dynamo_result = out_graph(*inps_rand)

        self.assertTrue(torch._dynamo.utils.same(real_result, dynamo_result))

    @patch.object(torch._dynamo.config, "capture_scalar_outputs", True)
    def test_zeroes_in_new_shape_scalar_out_permute(self):
        inp = torch.zeros(10)
        inp2 = torch.zeros(10)
        inp3 = torch.zeros(10)
        inps = [inp, inp2, inp3]

        inps_rand = [torch.randn(10), torch.randn(10), torch.randn(10)]

        def func(a, b, c):
            return b[0].item() + c[0].item() + a[0].item() + a[0].item()

        opt_func = torch._dynamo.optimize("eager", nopython=True)(func)
        real_result = opt_func(*inps_rand)

        torch._dynamo.reset()

        exported = torch._dynamo.export(func, *inps)
        out_graph = exported[0]

        dynamo_result = out_graph(*inps_rand)

        self.assertTrue(torch._dynamo.utils.same(real_result, dynamo_result))

    @patch.object(torch._dynamo.config, "capture_scalar_outputs", True)
    def test_zeroes_in_new_shape_scalar_out_permute_dupe_and_bypass(self):
        inp = torch.zeros(10)
        inp2 = torch.zeros(10)
        inp3 = torch.zeros(10)
        inps = [inp, inp2, inp3]

        inps_rand = [torch.randn(10), torch.randn(10), torch.randn(10)]

        def func(a, b, c):
            return a, b[0].item() + c[0].item() + a[0].item() + a[0].item(), a

        opt_func = torch._dynamo.optimize("eager", nopython=True)(func)
        real_result = opt_func(*inps_rand)

        torch._dynamo.reset()

        exported = torch._dynamo.export(func, *inps)
        out_graph = exported[0]

        dynamo_result = out_graph(*inps_rand)

        self.assertTrue(torch._dynamo.utils.same(real_result, dynamo_result))

    def test_func_return(self):
        inp = torch.zeros(10)
        inp2 = torch.zeros(10)
        inp3 = torch.zeros(10)
        inps = [inp, inp2, inp3]

        inps_rand = [torch.randn(10), torch.randn(10), torch.randn(10)]

        def func(a, b, c):
            x = a + b + c

            def func2(y):
                return x * y

            return func2(x)

        opt_func = torch._dynamo.optimize("eager", nopython=True)(func)
        real_result = opt_func(*inps_rand)

        torch._dynamo.reset()

        exported = torch._dynamo.export(func, *inps)
        out_graph = exported[0]

        dynamo_result = out_graph(*inps_rand)

        self.assertTrue(torch._dynamo.utils.same(real_result, dynamo_result))

    def test_dict_return(self):
        inp = torch.zeros(10)
        inp2 = torch.zeros(10)
        inp3 = torch.zeros(10)
        inps = [inp, inp2, inp3]

        inps_rand = [torch.randn(10), torch.randn(10), torch.randn(10)]

        def func(a, b, c):
            x = a + b + c
            return {"a": x}

        opt_func = torch._dynamo.optimize("eager", nopython=True)(func)
        real_result = opt_func(*inps_rand)

        torch._dynamo.reset()

        exported = torch._dynamo.export(func, *inps)
        out_graph = exported[0]

        dynamo_result = out_graph(*inps_rand)

        self.assertTrue(torch._dynamo.utils.same(real_result, dynamo_result))

    def test_export_with_aten_graph(self):
        def pre_attention_state_ops(input, mems, state):
            lc_key = state[0]
            lc_val = state[1]
            bar = []
            for i in range(0, 4):
                bar2 = []
                for j in range(0, 3):
                    bar2.append(
                        lc_key + lc_val + torch.tensor([0.1, 0.25, 0.4, 0.5, 0.1])
                    )
                bar.append(bar2)

            return bar

        def func():
            mems = torch.tensor([[[1.8364, 0.2724, -1.4917, -0.4367, 0.8640]]])
            state = [
                torch.tensor([[[1.0517, 0.3848, -0.6472, 0.0823, 0.9116]]]),
                torch.tensor([[[1.0517, 0.3848, -0.6472, 0.0823, 0.9116]]]),
            ]
            i = torch.tensor(
                [
                    [0.0313, -0.1487, -0.3846, -0.5321],
                    [-1.7073, 1.3331, -0.0890, -1.4935],
                    [-0.8314, -0.1862, -0.5935, 1.5232],
                ]
            )
            return pre_attention_state_ops(i, mems, state)

        opt_func = torch._dynamo.optimize("eager", nopython=True)(func)
        real_result = opt_func()

        torch._dynamo.reset()

        exported = torch._dynamo.export(func, aten_graph=True)
        out_graph = exported[0]

        dynamo_result = out_graph()
        self.assertTrue(torch._dynamo.utils.same(real_result, dynamo_result))

    def test_export_mismatched_out_with_aten_graph(self):
        def func(x):
            y = x + 1
            return ([x, x], (y, y))

        opt_func = torch._dynamo.optimize("eager", nopython=True)(func)
        real_result = opt_func(torch.tensor([[[1.3737, 0.1]]]))

        torch._dynamo.reset()

        exported = torch._dynamo.export(
            func, torch.tensor([[[1.3737, 0.1]]]), aten_graph=True
        )
        out_graph = exported[0]

        dynamo_result = out_graph(torch.tensor([[[1.3737, 0.1]]]))

        self.assertTrue(torch._dynamo.utils.same(real_result, dynamo_result))

    def test_export_graph_bypass_with_aten_graph(self):
        inp = [
            torch.tensor([0.1, 0.1]),
            torch.tensor([0.2, 0.2]),
            torch.tensor([0.3, 0.3]),
        ]

        def func(x):
            first = x[2]
            second = x[2]
            return first * second

        opt_func = torch._dynamo.optimize("eager", nopython=True)(func)
        real_result = opt_func(inp)

        torch._dynamo.reset()

        exported = torch._dynamo.export(func, inp, aten_graph=True)
        out_graph = exported[0]

        dynamo_result = out_graph(inp)

        self.assertTrue(torch._dynamo.utils.same(real_result, dynamo_result))

    def test_list_unpack_with_aten_graph(self):
        inp = [
            torch.tensor([0.1, 0.1]),
            torch.tensor([0.2, 0.2]),
            torch.tensor([0.3, 0.3]),
        ]

        def func(x):
            first = x[2]
            second = x[2]
            return x[0], first * second, x[1], x[2]

        opt_func = torch._dynamo.optimize("eager", nopython=True)(func)
        real_result = opt_func(inp)

        torch._dynamo.reset()

        exported = torch._dynamo.export(func, inp, aten_graph=True)
        out_graph = exported[0]

        dynamo_result = out_graph(inp)

        self.assertTrue(torch._dynamo.utils.same(real_result, dynamo_result))

    def test_export_mismatched_out_2_with_aten_graph(self):
        def func(x):
            y = x + 1
            return ([x, x], (y, y))

        opt_func = torch._dynamo.optimize("eager", nopython=True)(func)
        real_result = opt_func(torch.tensor([[[1.3737, 0.1]]]))

        torch._dynamo.reset()

        exported = torch._dynamo.export(
            func, torch.tensor([[[1.3737, 0.1]]]), aten_graph=True
        )
        out_graph = exported[0]

        dynamo_result = out_graph(torch.tensor([[[1.3737, 0.1]]]))

        self.assertTrue(torch._dynamo.utils.same(real_result, dynamo_result))

    def test_export_graph_with_list_with_aten_graph(self):
        inp = [
            torch.tensor([0.1, 0.1]),
            torch.tensor([0.2, 0.2]),
            torch.tensor([0.3, 0.3]),
            torch.tensor([0.4, 0.4]),
        ]

        def func(x):
            first = x[2]
            second = x[2]
            return first * second, x

        opt_func = torch._dynamo.optimize("eager", nopython=True)(func)
        real_result = opt_func(inp)

        torch._dynamo.reset()

        exported = torch._dynamo.export(func, inp, aten_graph=True)
        out_graph = exported[0]

        dynamo_result = out_graph(inp)

        self.assertTrue(torch._dynamo.utils.same(real_result, dynamo_result))

    def test_export_graph_with_complex_reorder_with_aten_graph(self):
        inp = [
            torch.tensor([0.1, 0.1]),
            torch.tensor([0.2, 0.2]),
            torch.tensor([0.3, 0.3]),
            torch.tensor([0.4, 0.4]),
        ]

        def func(x):
            first = x[0]
            second = x[1]
            third = x[2]
            return third, first, second, first * second, first * third

        opt_func = torch._dynamo.optimize("eager", nopython=True)(func)
        real_result = opt_func(inp)

        torch._dynamo.reset()

        exported = torch._dynamo.export(func, inp, aten_graph=True)
        out_graph = exported[0]

        dynamo_result = out_graph(inp)

        self.assertTrue(torch._dynamo.utils.same(real_result, dynamo_result))

    def test_dupes_with_aten_graph(self):
        inp = torch.tensor([0.1, 0.1])

        def func(x):
            y = x + 1
            return y, y

        opt_func = torch._dynamo.optimize("eager", nopython=True)(func)
        real_result = opt_func(inp)

        torch._dynamo.reset()

        exported = torch._dynamo.export(func, inp, aten_graph=True)
        out_graph = exported[0]

        dynamo_result = out_graph(inp)

        self.assertTrue(torch._dynamo.utils.same(real_result, dynamo_result))

    def test_dupes_2_with_aten_graph(self):
        inp = torch.tensor([0.1, 0.1])

        def func(x):
            y = x + 1
            return y, y

        opt_func = torch._dynamo.optimize("eager", nopython=True)(func)
        real_result = opt_func(inp)

        torch._dynamo.reset()

        exported = torch._dynamo.export(func, inp, aten_graph=True)
        out_graph = exported[0]

        dynamo_result = out_graph(inp)

        self.assertTrue(torch._dynamo.utils.same(real_result, dynamo_result))

    def test_dupes_and_bypass_with_aten_graph(self):
        inp = torch.tensor([0.1, 0.1])
        inp2 = torch.tensor([0.4, 0.4])
        inps = [inp, inp2]

        def func(x, z):
            y = x + 1
            return y, y, z

        opt_func = torch._dynamo.optimize("eager", nopython=True)(func)
        real_result = opt_func(*inps)

        torch._dynamo.reset()

        exported = torch._dynamo.export(func, *inps, aten_graph=True)
        out_graph = exported[0]

        dynamo_result = out_graph(*inps)

        self.assertTrue(torch._dynamo.utils.same(real_result, dynamo_result))

    def test_dupes_and_bypass_with_non_tensor_arg_with_aten_graph(self):
        inp = torch.tensor([0.1, 0.1])
        inp2 = torch.tensor([0.1, 0.1])
        inp3 = 4
        inps = [inp, inp2, inp3]

        def func(x, z, k):
            y = x + k
            return y, y, z

        opt_func = torch._dynamo.optimize("eager", nopython=True)(func)
        real_result = opt_func(*inps)

        torch._dynamo.reset()

        exported = torch._dynamo.export(func, *inps, aten_graph=True)
        out_graph = exported[0]

        dynamo_result = out_graph(*inps)

        self.assertTrue(torch._dynamo.utils.same(real_result, dynamo_result))

    def test_dupes_and_bypass_reorder_with_non_tensor_arg_with_aten_graph(self):
        inp = torch.tensor([0.1, 0.1])
        inp2 = torch.tensor([0.1, 0.1])
        inp3 = 4
        inps = [inp, inp2, inp3]

        def func(x, z, k):
            y = x + k
            return z, y, y

        opt_func = torch._dynamo.optimize("eager", nopython=True)(func)
        real_result = opt_func(*inps)

        torch._dynamo.reset()

        exported = torch._dynamo.export(func, *inps, aten_graph=True)
        out_graph = exported[0]

        dynamo_result = out_graph(*inps)

        self.assertTrue(torch._dynamo.utils.same(real_result, dynamo_result))

    @patch.object(torch._dynamo.config, "capture_scalar_outputs", True)
    def test_dupes_and_bypass_with_non_tensor_output_with_aten_graph(self):
        inp = torch.tensor([0.1, 0.1])
        inp2 = torch.tensor([0.1, 0.1])
        inp3 = 4
        inps = [inp, inp2, inp3]

        def func(x, z, k):
            y = x + k
            return y[0].item(), y, z

        opt_func = torch._dynamo.optimize("eager", nopython=True)(func)
        real_result = opt_func(*inps)

        torch._dynamo.reset()

        exported = torch._dynamo.export(func, *inps)
        out_graph = exported[0]

        dynamo_result = out_graph(*inps)

        self.assertTrue(torch._dynamo.utils.same(real_result, dynamo_result))

    def test_zeroes_in_and_out_different_shape_on_test_with_aten_graph(self):
        inp = torch.zeros(10)
        inp2 = torch.zeros(10)
        inp3 = torch.zeros(10)
        inps = [inp, inp2, inp3]

        inps_rand = [torch.randn(10), torch.randn(10), torch.randn(10)]

        def func(a, b, c):
            return [[a], [b, c], [a + b], [[c + c]]]

        opt_func = torch._dynamo.optimize("eager", nopython=True)(func)
        real_result = opt_func(*inps_rand)

        torch._dynamo.reset()

        exported = torch._dynamo.export(func, *inps, aten_graph=True)
        out_graph = exported[0]

        dynamo_result = out_graph(*inps_rand)

        self.assertTrue(torch._dynamo.utils.same(real_result, dynamo_result))

    def test_func_return_with_aten_graph(self):
        inp = torch.zeros(10)
        inp2 = torch.zeros(10)
        inp3 = torch.zeros(10)
        inps = [inp, inp2, inp3]

        inps_rand = [torch.randn(10), torch.randn(10), torch.randn(10)]

        def func(a, b, c):
            x = a + b + c

            def func2(y):
                return x * y

            return func2(x)

        opt_func = torch._dynamo.optimize("eager", nopython=True)(func)
        real_result = opt_func(*inps_rand)

        torch._dynamo.reset()

        exported = torch._dynamo.export(func, *inps, aten_graph=True)
        out_graph = exported[0]

        dynamo_result = out_graph(*inps_rand)

        self.assertTrue(torch._dynamo.utils.same(real_result, dynamo_result))

    def test_dict_return_with_aten_graph(self):
        inp = torch.zeros(10)
        inp2 = torch.zeros(10)
        inp3 = torch.zeros(10)
        inps = [inp, inp2, inp3]

        inps_rand = [torch.randn(10), torch.randn(10), torch.randn(10)]

        def func(a, b, c):
            x = a + b + c
            return {"a": x}

        opt_func = torch._dynamo.optimize("eager", nopython=True)(func)
        real_result = opt_func(*inps_rand)

        torch._dynamo.reset()

        exported = torch._dynamo.export(func, *inps, aten_graph=True)
        out_graph = exported[0]

        dynamo_result = out_graph(*inps_rand)

        self.assertTrue(torch._dynamo.utils.same(real_result, dynamo_result))

    def test_export_with_stack_trace(self):
        inp = torch.tensor([0.1, 0.1])

        class MyBlock(torch.nn.Module):
            def __init__(self):
                super().__init__()

            def forward(self, x):
                return torch.cos(x).relu()

        class MyModule(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.block = MyBlock()

            def forward(self, x):
                out = self.block(x)
                return out

        exported = torch._dynamo.export(MyModule(), inp, aten_graph=False)
        out_graph = exported[0]

        for node in out_graph.graph.nodes:
            if node.op not in {"placeholder", "output"}:
                self.assertTrue(node.stack_trace is not None)
                self.assertTrue(node.meta["nn_module_stack"] is not None)

        torch._dynamo.reset()

        exported = torch._dynamo.export(MyModule(), inp, aten_graph=True)
        out_graph = exported[0]
        for node in out_graph.graph.nodes:
            if node.op == "call_function":
                self.assertTrue(node.stack_trace is not None)
                self.assertTrue(node.meta["nn_module_stack"] is not None)

    def test_export_compare_optimize_with_make_fx(self):
        inp = torch.tensor([0.1, 0.1])
        linear = torch.nn.Linear(2, 2)

        def func(x):
            x = x + 1
            y = x.t()
            y = y.relu()
            y = linear(y)
            return y

        exported = torch._dynamo.export(func, inp, aten_graph=True)
        out_graph = exported[0]
        export_result = out_graph(inp)

        torch._dynamo.reset()

        def compiler(gm, sample_inputs):
            def fw(*args):
                aten_gm = make_fx(gm)(*args)
                return aten_gm(*args)

            return fw

        opt_func = torch._dynamo.optimize(compiler, nopython=True)(func)
        make_fx_result_through_backend = opt_func(inp)

        fx_g = make_fx(func)(inp)
        make_fx_result_through_direct = fx_g(inp)

        self.assertTrue(
            torch._dynamo.utils.same(make_fx_result_through_backend, export_result)
        )
        self.assertTrue(
            torch._dynamo.utils.same(make_fx_result_through_direct, export_result)
        )

    def test_export_with_constant_method_on_module(self):
        class MyModule(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.param = torch.nn.Parameter(torch.rand(4, 2))
                self.linear = torch.nn.Linear(2, 2)

            @torch._dynamo.assume_constant_result
            def helper_fn(self, x):
                return torch.nonzero(x)

            def forward(self, x):
                y = torch.sin(x)
                x = self.linear(x)
                y = self.helper_fn(x)
                return y

        module = MyModule()
        real_result = module(torch.tensor([[1.0, 0], [0, 0]]))
        module = MyModule()
        graph, _ = torch._dynamo.export(module, torch.tensor([[0.0, 0], [0, 0]]))
        result = graph(torch.tensor([[1.0, 0.0], [0, 0]]))
        self.assertTrue(torch._dynamo.utils.same(result, real_result))
        result = graph(torch.tensor([[1, 0], [0.25, 0.25]]))
        self.assertTrue(torch._dynamo.utils.same(result, real_result))

    def test_export_with_constant_method_on_module_invoke_twice(self):
        class MyModule(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.param = torch.nn.Parameter(torch.rand(4, 2))
                self.linear = torch.nn.Linear(2, 2)

            @torch._dynamo.assume_constant_result
            def helper_fn(self, x):
                return torch.nonzero(x)

            def forward(self, x):
                y = torch.sin(x)
                x = self.linear(x)
                y = self.helper_fn(x) + self.helper_fn(x)
                return y

        module = MyModule()
        real_result = module(torch.tensor([[1.0, 0], [0, 0]]))
        module = MyModule()
        graph, _ = torch._dynamo.export(module, torch.tensor([[0.0, 0], [0, 0]]))
        result = graph(torch.tensor([[1.0, 0.0], [0, 0]]))
        self.assertTrue(torch._dynamo.utils.same(result, real_result))
        result = graph(torch.tensor([[1, 0], [0.25, 0.25]]))
        self.assertTrue(torch._dynamo.utils.same(result, real_result))

    def test_export_with_constant_free_function(self):
        @torch._dynamo.assume_constant_result
        def helper_fn(x):
            return torch.nonzero(x)

        class MyModule(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.param = torch.nn.Parameter(torch.rand(4, 2))
                self.linear = torch.nn.Linear(2, 2)

            @torch._dynamo.assume_constant_result
            def helper_fn(self, x):
                return torch.nonzero(x)

            def forward(self, x):
                y = torch.sin(x)
                x = self.linear(x)
                y = helper_fn(x) + self.helper_fn(x)
                return y

        module = MyModule()
        real_result = module(torch.tensor([[1.0, 0], [0, 0]]))
        module = MyModule()
        graph, _ = torch._dynamo.export(module, torch.tensor([[0.0, 0], [0, 0]]))
        result = graph(torch.tensor([[1.0, 0.0], [0, 0]]))
        self.assertTrue(torch._dynamo.utils.same(result, real_result))
        result = graph(torch.tensor([[1, 0], [0.25, 0.25]]))
        self.assertTrue(torch._dynamo.utils.same(result, real_result))

    def test_export_with_constant_free_function_and_class_method(self):
        @torch._dynamo.assume_constant_result
        def helper_fn(x):
            return torch.nonzero(x)

        class MyModule(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.param = torch.nn.Parameter(torch.rand(4, 2))
                self.linear = torch.nn.Linear(2, 2)

            def forward(self, x):
                y = torch.sin(x)
                x = self.linear(x)
                y = helper_fn(x)
                return y

        module = MyModule()
        real_result = module(torch.tensor([[1.0, 0], [0, 0]]))
        module = MyModule()
        graph, _ = torch._dynamo.export(module, torch.tensor([[0.0, 0], [0, 0]]))
        result = graph(torch.tensor([[1.0, 0.0], [0, 0]]))
        self.assertTrue(torch._dynamo.utils.same(result, real_result))
        result = graph(torch.tensor([[1, 0], [0.25, 0.25]]))
        self.assertTrue(torch._dynamo.utils.same(result, real_result))

    def test_export_with_constant_free_function_and_class_method_multiarg(self):
        @torch._dynamo.assume_constant_result
        def helper_fn(x):
            return torch.nonzero(x)

        class MyModule(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.param = torch.nn.Parameter(torch.rand(4, 2))
                self.linear = torch.nn.Linear(2, 2)

            def forward(self, x, z):
                y = torch.sin(x)
                x = self.linear(x)
                y = helper_fn(x) + helper_fn(z)
                return y

        module = MyModule()
        real_result = module(
            torch.tensor([[1.0, 0], [0, 0]]), torch.tensor([[1.0, 0], [0, 0]])
        )
        module = MyModule()
        graph, _ = torch._dynamo.export(
            module, torch.tensor([[0.0, 0], [0, 0]]), torch.tensor([[1.0, 0], [0, 0]])
        )
        result = graph(
            torch.tensor([[1.0, 0.0], [0, 0]]), torch.tensor([[1.0, 0.0], [0, 0]])
        )
        self.assertTrue(torch._dynamo.utils.same(result, real_result))
        result = graph(
            torch.tensor([[1, 0], [0.25, 0.25]]), torch.tensor([[1, 0], [0.25, 0.25]])
        )
        self.assertTrue(torch._dynamo.utils.same(result, real_result))

    def test_export_with_constant_free_function_and_class_method_multiarg_diff(self):
        @torch._dynamo.assume_constant_result
        def helper_fn(x):
            return torch.nonzero(x)

        class MyModule(torch.nn.Module):
            def __init__(self):
                super().__init__()

            def forward(self, x, z):
                y = helper_fn(x) + helper_fn(z)
                return y

        module = MyModule()
        real_result = module(
            torch.tensor([[1.0, 0], [0, 0]]), torch.tensor([[1.0, 0], [0, 0]])
        )
        module = MyModule()
        graph, _ = torch._dynamo.export(
            module, torch.tensor([[0.0, 0], [0, 0]]), torch.tensor([[0.0, 0], [0.5, 0]])
        )
        result = graph(
            torch.tensor([[1.0, 0.0], [0, 0]]), torch.tensor([[0.0, 1.0], [0, 0]])
        )
        self.assertTrue(torch._dynamo.utils.same(result, real_result))
        result = graph(
            torch.tensor([[1, 0], [0.25, 0.25]]),
            torch.tensor([[0.33, 0.33], [0.25, 0.25]]),
        )
        self.assertTrue(torch._dynamo.utils.same(result, real_result))

    def test_export_with_constant_tuple_nonzero(self):
        class MyModule(torch.nn.Module):
            @torch._dynamo.assume_constant_result
            def helper_fn(self, x):
                return (torch.nonzero(x), torch.nonzero(x))

            def forward(self, x):
                y = torch.tensor([0.5])
                elements = self.helper_fn(x)
                all_y = []
                for element in elements:
                    for item in element:
                        all_y.append(y * item)
                return all_y

        module = MyModule()
        real_result = module(torch.tensor([1.0, 1.0]))
        graph, guards = torch._dynamo.export(module, torch.tensor([1.0, 1.0]))

        # Tensor input can be almost anything here, and the result will capture what we
        # made constant at compile time.
        result = graph(torch.tensor([[[1.0, 0], [0, 0]], [[1.0, 0], [0, 0]]]))
        self.assertTrue(torch._dynamo.utils.same(result, real_result))

    def test_export_with_constant_list_nonzero(self):
        class MyModule(torch.nn.Module):
            @torch._dynamo.assume_constant_result
            def helper_fn(self, x):
                return [torch.nonzero(x), torch.nonzero(x)]

            def forward(self, x):
                y = torch.tensor([0.5])
                elements = self.helper_fn(x)
                all_y = []
                for element in elements:
                    for item in element:
                        all_y.append(y * item)
                return all_y

        module = MyModule()
        real_result = module(torch.tensor([1.0, 1.0]))
        graph, guards = torch._dynamo.export(module, torch.tensor([1.0, 1.0]))

        # Tensor input can be almost anything here, and the result will capture what we
        # made constant at compile time.
        result = graph(torch.tensor([[[1.0, 0], [0, 0]], [[1.0, 0], [0, 0]]]))
        self.assertTrue(torch._dynamo.utils.same(result, real_result))

    def test_export_with_constant_list_nonzero_free_function(self):
        @torch._dynamo.assume_constant_result
        def helper_fn(x):
            return [torch.nonzero(x), torch.nonzero(x)]

        class MyModule(torch.nn.Module):
            def forward(self, x):
                y = torch.tensor([0.5])
                elements = helper_fn(x)
                all_y = []
                for element in elements:
                    for item in element:
                        all_y.append(y * item)
                return all_y

        module = MyModule()
        real_result = module(torch.tensor([1.0, 1.0]))
        graph, guards = torch._dynamo.export(module, torch.tensor([1.0, 1.0]))

        # Tensor input can be almost anything here, and the result will capture what we
        # made constant at compile time.
        result = graph(torch.tensor([[[1.0, 0], [0, 0]], [[1.0, 0], [0, 0]]]))
        self.assertTrue(torch._dynamo.utils.same(result, real_result))

    def test_export_with_constant_dict_values(self):
        class MyModule(torch.nn.Module):
            @torch._dynamo.assume_constant_result
            def helper_fn(self, x):
                return {"x": x, "x^2": x * x}

            def forward(self, x):
                y = torch.tensor([0.5])
                elements = self.helper_fn(x)
                y = y * elements["x"]
                y = y * elements["x^2"]
                return y

        module = MyModule()
        real_result = module(torch.tensor([2.0, 2.0]))
        graph, guards = torch._dynamo.export(module, torch.tensor([2.0, 2.0]))

        # Tensor input can be almost anything here, and the result will capture what we
        # made constant at compile time.
        result = graph(torch.tensor([[[1.0, 0], [0, 0]], [[1.0, 0], [0, 0]]]))
        self.assertTrue(torch._dynamo.utils.same(result, real_result))

    def test_export_with_constant_none_control_flow(self):
        class MyModule(torch.nn.Module):
            @torch._dynamo.assume_constant_result
            def helper_fn(self, x):
                if x.item() < 0:
                    return None
                else:
                    return x

            def forward(self, x):
                y = torch.tensor([0.5])
                x = self.helper_fn(x)
                if x is None:
                    return y
                return y * x

        module = MyModule()
        real_result = module(torch.tensor([-1]))

        # X is negative, so .item() < 0, which means we return y
        self.assertEqual(real_result, torch.tensor([0.5]))

        graph, guards = torch._dynamo.export(module, torch.tensor([-1]))
        result = graph(torch.tensor([2]))
        # X is positive, but we compiled helper_fn to return None, so it will still return y
        self.assertTrue(torch._dynamo.utils.same(result, real_result))

    def test_export_with_constant_not_none_control_flow(self):
        class MyModule(torch.nn.Module):
            @torch._dynamo.assume_constant_result
            def helper_fn(self, x):
                if x.item() < 0:
                    return None
                else:
                    return x

            def forward(self, x):
                y = torch.tensor([0.5])
                x = self.helper_fn(x)
                if x is None:
                    return y
                return y * x

        module = MyModule()
        real_result = module(torch.tensor([2]))

        # X is positive, so .item() > 0, which means we return y * x
        self.assertEqual(real_result, torch.tensor([1.0]))

        graph, guards = torch._dynamo.export(module, torch.tensor([2]))
        result = graph(torch.tensor([-0.5]))
        # X is negative, but we compiled helper_fn to return x, so it will still return y * x
        self.assertTrue(torch._dynamo.utils.same(result, real_result))

    def test_export_with_constant_none_control_flow_free_func(self):
        @torch._dynamo.assume_constant_result
        def helper_fn(x):
            if x.item() < 0:
                return None
            else:
                return x

        class MyModule(torch.nn.Module):
            def forward(self, x):
                y = torch.tensor([0.5])
                x = helper_fn(x)
                if x is None:
                    return y
                return y * x

        module = MyModule()
        real_result = module(torch.tensor([-1]))

        # X is negative, so .item() < 0, which means we return y
        self.assertEqual(real_result, torch.tensor([0.5]))

        graph, guards = torch._dynamo.export(module, torch.tensor([-1]))
        result = graph(torch.tensor([2]))
        # X is positive, but we compiled helper_fn to return None, so it will still return y
        self.assertTrue(torch._dynamo.utils.same(result, real_result))

    def test_export_with_constant_not_none_control_flow_pos(self):
        class MyModule(torch.nn.Module):
            @torch._dynamo.assume_constant_result
            def helper_fn(self, x):
                if x.item() < 0:
                    return None
                else:
                    return x

            def forward(self, x):
                y = torch.tensor([0.5])
                x = self.helper_fn(x)
                if x is None:
                    return y
                return y * x

        module = MyModule()
        real_result = module(torch.tensor([2]))

        # X is positive, so .item() > 0, which means we return y * x
        self.assertEqual(real_result, torch.tensor([1.0]))

        graph, guards = torch._dynamo.export(module, torch.tensor([2]))
        result = graph(torch.tensor([-0.5]))
        # X is negative, but we compiled helper_fn to return x, so it will still return y * x
        self.assertTrue(torch._dynamo.utils.same(result, real_result))

    def test_export_with_constant_not_none_control_flow_free_func(self):
        @torch._dynamo.assume_constant_result
        def helper_fn(x):
            if x.item() < 0:
                return None
            else:
                return x

        class MyModule(torch.nn.Module):
            def forward(self, x):
                y = torch.tensor([0.5])
                x = helper_fn(x)
                if x is None:
                    return y
                return y * x

        module = MyModule()
        real_result = module(torch.tensor([2]))

        # X is positive, so .item() > 0, which means we return y * x
        self.assertEqual(real_result, torch.tensor([1.0]))

        graph, guards = torch._dynamo.export(module, torch.tensor([2]))
        result = graph(torch.tensor([-0.5]))
        # X is negative, but we compiled helper_fn to return x, so it will still return y * x
        self.assertTrue(torch._dynamo.utils.same(result, real_result))

    def test_export_with_constant_not_return_const(self):
        class MyModule(torch.nn.Module):
            @torch._dynamo.assume_constant_result
            def helper_fn(self, x):
                return self.val

            def forward(self, x):
                y = torch.tensor([0.5])
                x = self.helper_fn(x)
                if x == "A":
                    return y
                return -1

        module = MyModule()
        module.val = "A"
        resA = module(torch.tensor([2]))
        graph, guards = torch._dynamo.export(module, torch.tensor([2]))
        module.val = "B"
        resB = graph(torch.tensor([2]))
        self.assertTrue(torch._dynamo.utils.same(resA, resB))

    def test_export_decomp(self):
        def f(x):
            return x.t() + x.t()

        def nop(x):
            return x.cos()

        graph, _ = torch._dynamo.export(
            f,
            (torch.randn(5)),
            aten_graph=True,
            decomposition_table={torch.ops.aten.t.default: nop},
        )
        self.assertEqual(
            len([n for n in graph.graph.nodes if n.target == torch.ops.aten.t.default]),
            0,
        )

        graph, _ = torch._dynamo.export(
            f, (torch.randn(5)), aten_graph=True, decomposition_table=None
        )
        self.assertEqual(
            len([n for n in graph.graph.nodes if n.target == torch.ops.aten.t.default]),
            2,
        )

    def test_export_decomp_asserts_bad_args(self):
        def f(x):
            return x.t() + x.t()

        def nop(x):
            return x.cos()

        with self.assertRaises(AssertionError):
            graph, _ = torch._dynamo.export(
                f,
                (torch.randn(5)),
                aten_graph=False,
                decomposition_table={torch.ops.aten.t.default: nop},
            )

    def test_export_decomp_asserts_bad_args_mode(self):
        def f(x):
            return x.t() + x.t()

        def nop(x):
            return x.cos()

        with self.assertRaises(AssertionError):
            graph, _ = torch._dynamo.export(
                f, (torch.randn(5)), aten_graph=False, tracing_mode="symbolic"
            )

    @patch.object(torch._dynamo.config, "capture_scalar_outputs", True)
    def test_export_with_module_layer(self):
        from functorch.experimental.control_flow import cond

        class Module(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.linear = torch.nn.Linear(3, 3)

            def forward(self, pred, x):
                def true_fn(val):
                    return self.linear(val) * torch.tensor(2)

                def false_fn(val):
                    return self.linear(val) * torch.tensor(-1)

                return cond(pred, true_fn, false_fn, [x])

        mod = Module()
        x = torch.randn([3, 3])
        pred = torch.tensor(x[0][0].item() < 0)
        real_result = mod.forward(pred, x)

        torch._dynamo.reset()

        exported = torch._dynamo.export(mod.forward, pred, x)
        out_graph = exported[0]

        dynamo_result = out_graph(pred, x)
        self.assertTrue(torch._dynamo.utils.same(real_result, dynamo_result))

        # New X, just to show we did not specialize
        x = x * -1
        pred = torch.tensor(x[0][0].item() < 0)
        real_result_2 = mod.forward(pred, x)
        dynamo_result_2 = out_graph(pred, x)
        self.assertTrue(torch._dynamo.utils.same(real_result_2, dynamo_result_2))

    @patch.object(torch._dynamo.config, "dynamic_shapes", True)
    def test_export_with_map_cond(self):
        from functorch.experimental.control_flow import cond, map

        class Module(torch.nn.Module):
            def __init__(self):
                super().__init__()

            def inner(self, x, pred):
                def true_fn(x):
                    return x + x

                def false_fn(x):
                    return x * x

                return cond(pred, true_fn, false_fn, [x])

            def forward(self, pred, xs):
                def body(x, pred):
                    return self.inner(x, pred)

                return map(body, xs, pred)

        mod = Module()
        x = torch.randn(3, 2, 1)
        pred_x = torch.tensor(True)

        y = torch.randn(4, 3, 2)
        pred_y = torch.tensor(False)
        real_result = mod(pred_y, y)

        out_graph, _ = torch._dynamo.export(mod, pred_x, x)
        self.assertEqual(real_result, out_graph(pred_y, y))

    @patch.object(torch._dynamo.config, "dynamic_shapes", True)
    def test_export_with_map_zero_sized_tensor(self):
        from functorch.experimental.control_flow import map

        class Module(torch.nn.Module):
            def __init__(self):
                super().__init__()

            def forward(self, xs):
                def body(x):
                    return x + 1

                return map(body, xs)

        mod = Module()
        xs = torch.randn(0, 2)
        with self.assertRaisesRegex(
            torch._dynamo.exc.Unsupported,
            "zero-sized tensor",
        ):
            out_graph, _ = torch._dynamo.export(mod, xs)

    def test_export_meta_val(self):
        def f(x, y, z):
            return x * y + z

        gm, _ = torch._dynamo.export(
            f,
            torch.ones(3, 2),
            torch.zeros(3, 2),
            torch.ones(3, 2),
            aten_graph=True,
            tracing_mode="symbolic",
        )
        for node in gm.graph.nodes:
            if node.op == "placeholder":
                self.assertIn("val", node.meta)

    def test_input_container_type(self):
        def f(x: torch.Tensor, y: List[torch.Tensor]) -> Dict[str, torch.Tensor]:
            return {"a": x.sum() + sum(y).sum()}

        inp = (torch.randn(6, 5), [torch.randn(6, 5), torch.randn(6, 5)])

        gm, _ = torch._dynamo.export(f, *inp, aten_graph=True, tracing_mode="symbolic")

        self.assertEqual(gm(*inp), f(*inp))

    def test_export_symbolic_shape(self):
        def f(x: torch.Tensor) -> torch.Tensor:
            return torch.empty(x.shape[0] * 2)

        inp = (torch.randn(6, 5),)
        gm, _ = torch._dynamo.export(f, *inp, aten_graph=True, tracing_mode="symbolic")

        has_sym_size = False
        for node in gm.graph.nodes:
            if node.target is torch.ops.aten.sym_size:
                has_sym_size = True

        self.assertTrue(has_sym_size)

    @patch.object(torch._dynamo.config, "dynamic_shapes", True)
    def test_dynamic_slicing(self):
        def f(x):
            return x[: x.shape[0] - 2, x.shape[1] - 1 :: 2]

        gm_aten_mode, _ = torch._dynamo.export(
            f, torch.randn(4, 5), aten_graph=True, tracing_mode="symbolic"
        )

        inp = torch.randn(6, 7)
        self.assertEqual(gm_aten_mode(inp).shape, f(inp).shape)

        count = 0
        # aten graph should flatten getitem calls to actual
        # slice kernel call.
        for node in gm_aten_mode.graph.nodes:
            if (
                node.op == "call_function"
                and node.target == torch.ops.aten.slice.Tensor
            ):
                count += 1

        self.assertEqual(count, 2)

        gm_torch_mode, _ = torch._dynamo.export(f, torch.randn(4, 5), aten_graph=False)

        # In torch mode, the graph should contain 3 getitem methods
        # one for x.shape[0]-2 and one for x.shape[1]-1 and one for slice
        # this is because Tensor class has its' own getitem method
        # which gets translated to aten.Slice later.
        count = 0
        for node in gm_torch_mode.graph.nodes:
            if node.op == "call_function" and node.target == operator.getitem:
                count += 1

        self.assertEqual(count, 3)
        self.assertEqual(gm_torch_mode(inp).shape, f(inp).shape)

    @patch.object(torch._dynamo.config, "dynamic_shapes", True)
    def test_dynamic_slicing_invalid(self):
        def g(x, y):
            return x[y : x.shape[0]]

        with self.assertRaisesRegex(
            torch._dynamo.exc.Unsupported,
            "Dynamic slicing on data-dependent value is not supported",
        ):
            torch._dynamo.export(
                g,
                torch.randn(4, 5),
                torch.tensor(2),
                aten_graph=True,
                tracing_mode="symbolic",
            )

    @patch.object(torch._dynamo.config, "dynamic_shapes", True)
    def test_dynamic_slicing_simple(self):
        def f(x):
            return x[slice(None, None, None)]

        gm, _ = torch._dynamo.export(
            f, torch.randn(4, 5), aten_graph=True, tracing_mode="symbolic"
        )

        inp = torch.randn(6, 7)
        self.assertEqual(gm(inp), f(inp))

    def test_export_cond_in_aten_symbolic(self):
        class ConditionOp(torch.nn.Module):
            def __init__(self):
                super().__init__()

            def true_fn(self, x, y):
                return x * y

            def false_fn(self, x, y):
                return x + y

            def forward(self, pred, x, y):
                return cond(pred, self.true_fn, self.false_fn, [x, y])

        model = ConditionOp()
        inp = (
            torch.tensor(False),
            torch.randn(4, 4),
            torch.randn(4, 4),
        )
        gm, _ = torch._dynamo.export(
            model, *inp, aten_graph=True, tracing_mode="symbolic"
        )

        gm.print_readable()

        self.assertEqual(gm(*inp), model(*inp))


if __name__ == "__main__":
    from torch._dynamo.test_case import run_tests

    run_tests()
