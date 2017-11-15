import unittest

import numpy

import chainer
from chainer import cuda
from chainer import functions
from chainer import gradient_check
from chainer import testing
from chainer.testing import attr


@testing.parameterize(*testing.product({
    'shape_axis':
        [{'shape': None, 'axis': 1}, ] +
        testing.product({'shape': ((2, 3),), 'axis': (0, 1)}) +
        testing.product({'shape': ((2, 3, 4),), 'axis': (0, 2)}) +
        testing.product({'shape': ((2, 3, 2, 3),), 'axis': (1, 3)}),
    'dtype': [numpy.float16, numpy.float32, numpy.float64],
}))
@testing.fix_random()
class TestSoftmax(unittest.TestCase):

    def setUp(self):
        self.shape = self.shape_axis['shape']
        self.axis = self.shape_axis['axis']
        if self.shape is None:
            # For checking numerical stability
            value = -5 if self.dtype == numpy.float16 else -1000
            self.x = numpy.array([[value, 1]], dtype=self.dtype)
        else:
            self.x = numpy.random.uniform(-1, 1, self.shape).astype(self.dtype)
        self.gy = numpy.random.uniform(-1, 1, self.x.shape).astype(self.dtype)
        self.ggx = numpy.random.uniform(-1, 1, self.x.shape).astype(self.dtype)

        self.check_forward_options = {}
        self.check_backward_options = {}
        self.check_double_backward_options = {}
        if self.dtype == numpy.float16:
            self.check_forward_options = {'atol': 1e-3, 'rtol': 1e-2}
            self.check_backward_options = {'atol': 1e-3, 'rtol': 1e-2}
            self.check_double_backward_options = {'atol': 1e-3, 'rtol': 1e-2}

    def check_forward(self, x_data, use_cudnn='always'):
        x = chainer.Variable(x_data)
        with chainer.using_config('use_cudnn', use_cudnn):
            y = functions.softmax(x, axis=self.axis)
        self.assertEqual(y.data.dtype, self.dtype)

        y_expect = numpy.exp(self.x)
        y_roll = numpy.rollaxis(y_expect, self.axis, y_expect.ndim)
        for i in numpy.ndindex(y_roll.shape[:-1]):
            y_roll[i] /= y_roll[i].sum()

        testing.assert_allclose(
            y_expect, y.data, **self.check_forward_options)

    def test_forward_cpu(self):
        self.check_forward(self.x)

    @attr.gpu
    def test_forward_gpu(self):
        self.check_forward(cuda.to_gpu(self.x))

    @attr.gpu
    def test_forward_gpu_non_contiguous(self):
        self.check_forward(
            cuda.cupy.asfortranarray(cuda.to_gpu(self.x)))

    @attr.gpu
    def test_forward_gpu_no_cudnn(self):
        self.check_forward(cuda.to_gpu(self.x), 'never')

    def check_backward(self, x_data, gy_data, use_cudnn='always'):
        def f(x):
            return functions.softmax(x, axis=self.axis)

        with chainer.using_config('use_cudnn', use_cudnn):
            gradient_check.check_backward(
                f, x_data, gy_data, dtype=numpy.float64,
                **self.check_backward_options)

    def test_backward_cpu(self):
        self.check_backward(self.x, self.gy)

    @attr.gpu
    def test_backward_gpu(self):
        self.check_backward(cuda.to_gpu(self.x), cuda.to_gpu(self.gy))

    @attr.gpu
    def test_backward_gpu_non_contiguous(self):
        self.check_backward(
            cuda.cupy.asfortranarray(cuda.to_gpu(self.x)),
            cuda.cupy.asfortranarray(cuda.to_gpu(self.gy)))

    @attr.gpu
    def test_backward_gpu_no_cudnn(self):
        self.check_backward(cuda.to_gpu(self.x), cuda.to_gpu(self.gy), 'never')

    def check_double_backward(self, x_data, gy_data, ggx_data,
                              use_cudnn='always'):
        def f(x):
            return functions.softmax(x, axis=self.axis)

        with chainer.using_config('use_cudnn', use_cudnn):
            gradient_check.check_double_backward(
                f, (x_data,), (gy_data,), (ggx_data), dtype=numpy.float64,
                **self.check_double_backward_options)

    def test_double_backward_cpu(self):
        self.check_double_backward(self.x, self.gy, self.ggx)

    @attr.gpu
    def test_double_backward_gpu(self):
        self.check_double_backward(
            cuda.to_gpu(self.x), cuda.to_gpu(self.gy), cuda.to_gpu(self.ggx))

    @attr.gpu
    def test_double_backward_gpu_no_cudnn(self):
        self.check_double_backward(
            cuda.to_gpu(self.x), cuda.to_gpu(self.gy), cuda.to_gpu(self.ggx),
            'never')


@testing.parameterize(*testing.product({
    'axis': [0],
    'use_cudnn': ['always', 'auto', 'never'],
    'dtype': [numpy.float16, numpy.float32, numpy.float64],
}))
@attr.cudnn
class TestSoftmaxCudnnCall(unittest.TestCase):

    def setUp(self):
        self.x = cuda.cupy.random.uniform(-1, 1, (2, 3)).astype(self.dtype)
        self.gy = cuda.cupy.random.uniform(-1, 1, (2, 3)).astype(self.dtype)
        with chainer.using_config('use_cudnn', self.use_cudnn):
            self.expect = chainer.should_use_cudnn('>=auto')

    def forward(self):
        x = chainer.Variable(self.x)
        return functions.softmax(x, axis=self.axis)

    def test_call_cudnn_forward(self):
        with chainer.using_config('use_cudnn', self.use_cudnn):
            with testing.patch('cupy.cuda.cudnn.softmaxForward') as func:
                self.forward()
                self.assertEqual(func.called, self.expect)

    def test_call_cudnn_backward(self):
        with chainer.using_config('use_cudnn', self.use_cudnn):
            y = self.forward()
            y.grad = self.gy
            with testing.patch('cupy.cuda.cudnn.softmaxBackward') as func:
                y.backward()
                self.assertEqual(func.called, self.expect)


testing.run_module(__name__, __file__)
