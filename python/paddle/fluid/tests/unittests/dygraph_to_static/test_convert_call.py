#   Copyright (c) 2019 PaddlePaddle Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
import unittest

import numpy as np
from test_program_translator import get_source_code

import paddle
import paddle.fluid as fluid
import paddle.jit.dy2static as _jst
from paddle.jit.dy2static.convert_call_func import CONVERSION_OPTIONS

SEED = 2020
np.random.seed(SEED)

# Situation 1 : test recursive call


# Use a decorator to test exception
@paddle.jit.to_static
def dyfunc_with_if(x_v):
    if paddle.mean(x_v).numpy()[0] > 5:
        x_v = x_v - 1
    else:
        x_v = x_v + 1
    return x_v


@paddle.jit.to_static
def nested_func(x_v):
    x_v = fluid.dygraph.to_variable(x_v)

    def fn1():
        return x_v

    res = fn1()
    return res


@paddle.jit.to_static
def dyfunc_with_third_library_logging(x_v):
    logging.info('test dyfunc_with_third_library_logging')
    if paddle.mean(x_v).numpy()[0] > 5:
        x_v = x_v - 1
    else:
        x_v = x_v + 1
    return x_v


class A:
    @staticmethod
    def add(a, b):
        """
        dygraph mode, return a numpy object.
        static graph mode, return a variable object.
        """
        return paddle.to_tensor(a.numpy() + b.numpy())


@paddle.jit.to_static
def dyfunc_with_staticmethod(x_v):
    a = A()
    return a.add(x_v, x_v)


class TestRecursiveCall1(unittest.TestCase):
    def setUp(self):
        self.input = np.random.random([10, 16]).astype('float32')
        self.place = (
            fluid.CUDAPlace(0)
            if fluid.is_compiled_with_cuda()
            else fluid.CPUPlace()
        )
        self.init_test_func()

    def init_test_func(self):
        self.dyfunc = nested_func

    def get_dygraph_output(self):
        paddle.jit.enable_to_static(False)
        with fluid.dygraph.guard():
            res = self.dyfunc(self.input).numpy()
            return res

    def get_static_output(self):
        paddle.jit.enable_to_static(True)
        with fluid.dygraph.guard():
            res = self.dyfunc(self.input).numpy()
            return res

    def test_transformed_static_result(self):
        static_res = self.get_static_output()
        dygraph_res = self.get_dygraph_output()
        np.testing.assert_allclose(
            dygraph_res,
            static_res,
            rtol=1e-05,
            err_msg='dygraph res is {}\nstatic_res is {}'.format(
                dygraph_res, static_res
            ),
        )


lambda_fun = lambda x: x


class MyConvLayer(fluid.dygraph.Layer):
    def __init__(self):
        super().__init__()
        self._conv = paddle.nn.Conv2D(
            in_channels=3,
            out_channels=2,
            kernel_size=3,
            weight_attr=paddle.ParamAttr(
                initializer=paddle.nn.initializer.Constant(value=0.99)
            ),
            bias_attr=paddle.ParamAttr(
                initializer=paddle.nn.initializer.Constant(value=0.5)
            ),
        )

    @paddle.jit.to_static
    def forward(self, inputs):
        y = dyfunc_with_if(inputs)
        y = lambda_fun(y)
        y = self.dymethod(y)
        return y

    @paddle.jit.to_static
    def dymethod(self, x_v):
        x_v = fluid.layers.assign(x_v)
        return x_v


class MyLayer(fluid.dygraph.Layer):
    def __init__(self):
        super().__init__()

        self.conv = MyConvLayer()
        self.fc = paddle.nn.Linear(
            in_features=5,
            out_features=1,
            weight_attr=paddle.ParamAttr(
                initializer=paddle.nn.initializer.Constant(value=0.99)
            ),
            bias_attr=paddle.ParamAttr(
                initializer=paddle.nn.initializer.Constant(value=0.5)
            ),
        )
        self.act = paddle.nn.ReLU()

    @paddle.jit.to_static
    def forward(self, inputs):
        h = self.conv(inputs)
        out = self.fc(h)
        return self.act(out)


class TestRecursiveCall2(unittest.TestCase):
    def setUp(self):
        self.input = np.random.random((1, 3, 3, 5)).astype('float32')
        self.place = (
            fluid.CUDAPlace(0)
            if fluid.is_compiled_with_cuda()
            else fluid.CPUPlace()
        )
        self.set_func()

    def set_func(self):
        self.dygraph_func = MyLayer()

    def _run(self):
        with fluid.dygraph.guard():
            data = fluid.dygraph.to_variable(self.input)
            res = self.dygraph_func(data)

            return res.numpy()

    def get_dygraph_output(self):
        paddle.jit.enable_to_static(False)
        return self._run()

    def get_static_output(self):
        paddle.jit.enable_to_static(True)
        return self._run()

    def test_transformed_static_result(self):
        dygraph_res = self.get_dygraph_output()
        static_res = self.get_static_output()
        np.testing.assert_allclose(dygraph_res, static_res, rtol=1e-05)


class TestThirdPartyLibrary(TestRecursiveCall2):
    def set_func(self):
        self.dygraph_func = dyfunc_with_third_library_logging


class TestStaticMethod(TestRecursiveCall2):
    def set_func(self):
        self.dygraph_func = dyfunc_with_staticmethod


# Situation 2 : test not_to_static


def func_sum(x):
    res = paddle.sum(x)
    return res


@paddle.jit.not_to_static
def func_not_to_static(x):
    res = func_sum(x)
    return res


@paddle.jit.to_static
def func_convert_then_not_to_static(x):
    y = func_not_to_static(x)
    return y


class TestClass(paddle.nn.Layer):
    @paddle.jit.not_to_static
    def called_member(self, x):
        return paddle.sum(x)

    @paddle.jit.to_static
    def forward(self, x):
        y = self.called_member(x)
        return y


class TestNotToConvert(TestRecursiveCall2):
    def set_func(self):
        self.dygraph_func = func_not_to_static

    def test_conversion_options(self):
        options = getattr(self.dygraph_func, CONVERSION_OPTIONS, None)
        self.assertIsNotNone(options)
        self.assertTrue(options.not_convert)


class TestNotToConvert2(TestRecursiveCall2):
    def set_func(self):
        self.dygraph_func = func_convert_then_not_to_static


class TestNotToConvert3(TestRecursiveCall2):
    def set_func(self):
        self.dygraph_func = TestClass()


class TestDynamicToStaticCode(unittest.TestCase):
    def setUp(self):
        self.set_func()
        self.set_answer_func()

    def set_func(self):
        self.func = func_not_to_static

    def set_answer_func(self):
        class StaticCode:
            @paddle.jit.not_to_static
            def func_not_to_static(x):
                res = func_sum(x)
                return res

        self.answer_func = StaticCode.func_not_to_static

    def _get_answer_code(self):
        return get_source_code(self.answer_func)

    def _get_transformed_code(self):
        transformed_func = _jst.Call(self.func)
        return get_source_code(transformed_func)

    def test_code(self):
        transformed_code = self._get_transformed_code()
        answer_code = self._get_answer_code()
        self.assertEqual(
            answer_code,
            transformed_code,
            msg="\ntransformed_code : \n{}\nanswer_code : \n{}".format(
                transformed_code, answer_code
            ),
        )


class TestDynamicToStaticCode2(TestDynamicToStaticCode):
    def set_func(self):
        self.func = func_convert_then_not_to_static

    def set_answer_func(self):
        class StaticCode:
            def func_convert_then_not_to_static(x):
                __return_value_0 = None
                y = _jst.Call(func_not_to_static)(x)
                __return_value_0 = y
                return __return_value_0

        self.answer_func = StaticCode.func_convert_then_not_to_static


if __name__ == '__main__':
    unittest.main()
