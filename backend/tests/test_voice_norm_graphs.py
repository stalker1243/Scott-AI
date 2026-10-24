"""Bounded graph behavior without GPU, SDK, network or personal audio.

Real CUDA tensor/audio equivalence is separately recorded in the GPU report.
"""
import ast
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import sys

import numpy as np
import pytest

pytestmark = pytest.mark.unit


@dataclass(frozen=True)
class Device:
    index: int = 0


@pytest.fixture
def rig(monkeypatch):
    source = Path(__file__).resolve().parents[2]/'voice/runtime/voice_worker.py'
    tree = ast.parse(source.read_text(encoding='utf-8'))
    functions = [node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='_cuda_norm_graphs']
    namespace = {}
    if functions:
        exec(compile(ast.Module(body=functions,type_ignores=[]),str(source),'exec'),namespace)
    state = SimpleNamespace(grad=False,capturing=False,graph=None,current=None,graphs=[],
        streams=[],norm_calls=0,replay_fail=False,capture_fail=False,bad_result=False)
    bf16,fp32 = object(),object()

    class Tensor:
        def __init__(self,values):
            self.data = np.array(values,dtype=np.float32,copy=True)
            self.device = Device()
            self.dtype = bf16
            self.is_cuda = True
            self.contiguous = True
        @property
        def shape(self):
            return self.data.shape
        def numel(self):
            return self.data.size
        def is_contiguous(self):
            return self.contiguous
        def copy_(self,other):
            self.data[...] = other.data
            return self
        def clone(self):
            return Tensor(self.data)

    class Stream:
        def __init__(self,device=None):
            self.cuda_stream = len(state.streams)
            state.streams.append(self)
        def wait_stream(self,other):
            pass
        def synchronize(self):
            pass

    class Graph:
        def __init__(self):
            self.calls = 0
            self.run = None
            state.graphs.append(self)
        def replay(self):
            self.calls += 1
            if state.replay_fail:
                raise RuntimeError('Replay failed')
            self.run()

    @contextmanager
    def stream_context(value):
        previous = state.current
        state.current = value
        try:
            yield
        finally:
            state.current = previous

    @contextmanager
    def capture(graph,*,stream):
        if state.capture_fail:
            raise RuntimeError('Capture failed')
        state.capturing,state.graph = True,graph
        try:
            with stream_context(stream):
                yield
        finally:
            state.capturing,state.graph = False,None

    class Norm:
        def __init__(self,size=1024,eps=1e-6):
            self.weight = Tensor(np.ones(size))
            self.variance_epsilon = eps
        def eval(self):
            return self
        def forward(self,values):
            state.norm_calls += 1
            def calculate():
                signal = values.data
                return self.weight.data*signal/np.sqrt(np.mean(signal**2,axis=-1,keepdims=True)+self.variance_epsilon)
            output = Tensor(calculate())
            if state.capturing and state.graph is not None:
                def replay():
                    output.data[...] = calculate()+(1 if state.bad_result else 0)
                state.graph.run = replay
            return output
        def __call__(self,values):
            return self.forward(values)
    Norm.__module__ = 'qwen_tts.core.models.modeling_qwen3_tts'
    state.current = Stream()
    torch = SimpleNamespace(__version__='2.14.1+cu126',bfloat16=bf16,
        is_grad_enabled=lambda:state.grad,empty_like=lambda value:Tensor(np.zeros_like(value.data)),
        equal=lambda a,b:np.array_equal(a.data,b.data),nn=SimpleNamespace(Parameter=lambda value,**kw:value),
        cuda=SimpleNamespace(Stream=Stream,CUDAGraph=Graph,stream=stream_context,graph=capture,
            current_stream=lambda device:state.current,is_current_stream_capturing=lambda:state.capturing))
    monkeypatch.setitem(sys.modules,'torch',torch)
    modules = [Norm() for _ in range(134)]
    model = SimpleNamespace(modules=lambda:iter(modules))
    def attach():
        assert '_cuda_norm_graphs' in namespace,'Bounded CUDA norm graph path is absent'
        return namespace['_cuda_norm_graphs'](model,Norm)
    return SimpleNamespace(attach=attach,modules=modules,model=model,Norm=Norm,Tensor=Tensor,
        torch=torch,state=state,bf16=bf16,fp32=fp32,Stream=Stream)


@pytest.mark.parametrize('shape',[(1,1,1024),(1,2,1024),(1,1,16,128),(1,2,16,128),(1,1,8,128),(1,2,8,128)])
def test_supported_shapes_replay_original_result_in_fresh_output(rig,shape):
    owner = rig.modules[0]
    owner.weight = rig.Tensor(np.linspace(.5,1.5,shape[-1]))
    values = rig.Tensor(np.linspace(-2,2,np.prod(shape)).reshape(shape))
    expected = owner(values).data.copy()
    forward = rig.Norm.forward
    cache = rig.attach()
    first = owner(values)
    second = owner(values)
    assert len(cache)==1 and len(rig.state.graphs)==1
    assert rig.state.graphs[0].calls==2
    assert np.array_equal(first.data,expected) and np.array_equal(second.data,expected)
    assert first is not second and not np.shares_memory(first.data,second.data)
    assert rig.Norm.forward is forward


def test_shared_graph_copies_each_layers_trained_weights_and_retained_outputs(rig):
    a,b = rig.modules[:2]
    a.weight.data *= 2
    b.weight.data *= 3
    a_values = rig.Tensor(np.linspace(-1,1,1024).reshape(1,1,1024))
    b_values = rig.Tensor(np.linspace(2,3,1024).reshape(1,1,1024))
    a_expected,b_expected = a(a_values).data.copy(),b(b_values).data.copy()
    weights = [module.weight.data.copy() for module in (a,b)]
    cache = rig.attach()
    result = a(a_values)
    other = b(b_values)
    assert np.array_equal(result.data,a_expected) and np.array_equal(other.data,b_expected)
    assert np.array_equal(result.data,a_expected)  # Later layer must not overwrite it.
    assert len(cache)==1 and len(rig.state.graphs)==1
    assert all(np.array_equal(module.weight.data,expected) for module,expected in zip((a,b),weights))


@pytest.mark.parametrize('kind',['grad','cpu','dtype','shape','noncontiguous','weight_cpu','weight_device',
    'weight_dtype','weight_noncontiguous','weight_shape','epsilon','nested_capture'])
def test_unsupported_inputs_keep_original_forward_without_allocating_graph(rig,kind):
    owner = rig.modules[0]
    values = rig.Tensor(np.ones((1,1,1024)))
    if kind=='grad':rig.state.grad=True
    elif kind=='cpu':values.is_cuda=False
    elif kind=='dtype':values.dtype=rig.fp32
    elif kind=='shape':values=rig.Tensor(np.ones((1,3,1024)))
    elif kind=='noncontiguous':values.contiguous=False
    elif kind=='weight_cpu':owner.weight.is_cuda=False
    elif kind=='weight_device':owner.weight.device=Device(1)
    elif kind=='weight_dtype':owner.weight.dtype=rig.fp32
    elif kind=='weight_noncontiguous':owner.weight.contiguous=False
    elif kind=='weight_shape':owner.weight=rig.Tensor(np.ones((1,1024)))
    elif kind=='epsilon':owner.variance_epsilon=1e-5
    elif kind=='nested_capture':rig.state.capturing=True
    expected = owner(values).data.copy()
    cache = rig.attach()
    result = owner(values)
    assert np.array_equal(result.data,expected)
    assert not cache and not rig.state.graphs


def test_other_thread_keeps_original_forward(rig):
    owner = rig.modules[0]
    values = rig.Tensor(np.ones((1,1,1024)))
    expected = owner(values).data.copy()
    cache = rig.attach()
    with ThreadPoolExecutor(max_workers=1) as pool:
        result = pool.submit(owner,values).result(timeout=2)
    assert np.array_equal(result.data,expected) and not cache and not rig.state.graphs


@pytest.mark.parametrize('kind',['torch_version','module','forward','model_count'])
def test_unknown_runtime_or_model_does_not_patch_instances_or_class(rig,kind):
    if kind=='torch_version':rig.torch.__version__='future'
    elif kind=='module':rig.Norm.__module__='other_model'
    elif kind=='forward':
        def fused(self,values):return values
        rig.Norm.forward=fused
    elif kind=='model_count':rig.modules.pop()
    before = [module.forward.__func__ for module in rig.modules]
    assert rig.attach() is None
    assert [module.forward.__func__ for module in rig.modules]==before
    assert not rig.state.graphs


def test_cache_is_per_stream_and_bounded_at_eight_entries(rig):
    owner = rig.modules[0]
    values = rig.Tensor(np.ones((1,1,1024)))
    expected = owner(values).data.copy()
    cache = rig.attach()
    for _ in range(10):
        rig.state.current=rig.Stream()
        assert np.array_equal(owner(values).data,expected)
    assert len(cache)==8 and len(rig.state.graphs)==8
    assert len({key[1] for key in cache})==8


def test_caches_belong_to_their_model_instance(rig):
    values = rig.Tensor(np.ones((1,1,1024)))
    first = rig.attach()
    rig.modules[0](values)
    other_modules = [rig.Norm() for _ in range(134)]
    rig.modules[:] = other_modules
    second = rig.attach()
    rig.modules[0](values)
    assert first is not second and len(first)==len(second)==1
    assert len(rig.state.graphs)==2


def test_first_mismatch_disables_shape_and_returns_exact_original(rig):
    owner = rig.modules[0]
    values = rig.Tensor(np.ones((1,1,1024)))
    expected = owner(values).data.copy()
    rig.state.bad_result=True
    cache = rig.attach()
    first = owner(values)
    second = owner(values)
    assert np.array_equal(first.data,expected) and np.array_equal(second.data,expected)
    assert list(cache.values())==[None]
    assert len(rig.state.graphs)==1 and rig.state.graphs[0].calls==1


@pytest.mark.parametrize('kind',['capture','replay'])
def test_cuda_failures_propagate_without_unsafe_retry(rig,kind):
    owner = rig.modules[0]
    cache = rig.attach()
    values = rig.Tensor(np.ones((1,1,1024)))
    if kind=='capture':rig.state.capture_fail=True
    else:rig.state.replay_fail=True
    with pytest.raises(RuntimeError,match='failed'):
        owner(values)
    assert not cache and len(rig.state.graphs)==1
