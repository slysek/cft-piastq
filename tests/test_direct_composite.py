from __future__ import annotations

import threading
from collections.abc import Sequence
from dataclasses import dataclass
from numbers import Integral
from types import SimpleNamespace
from typing import Any

import pytest
from qiskit.primitives import SamplerResult
from qiskit.result import QuasiDistribution

from cft_piastq.direct_composite import (
    DIRECT_SHOT_LIMIT,
    DirectCompositeJob,
    aggregate_direct_results,
    exact_counts_from_sampler_result,
    partition_direct_shots,
)
from cft_piastq.errors import DirectProviderError, PiastQTimeoutError


def sampler_result(*items: dict[int, float]) -> SamplerResult:
    return SamplerResult(
        [QuasiDistribution(item) for item in items],
        metadata=[{} for _ in items],
    )


class HostileClassAccess:
    @property
    def __class__(self) -> type[object]:
        raise DirectProviderError("provider payload")


@dataclass
class ChildPlan:
    outcome: SamplerResult | BaseException
    gate: threading.Event | None = None
    cancel_status: object = "cancelled"
    cancel_error: BaseException | None = None
    cancel_started: threading.Event | None = None
    cancel_gate: threading.Event | None = None
    release_result_on_cancel: bool = True


class RecordingChildJob:
    def __init__(self, sampler: RecordingSampler, plan: ChildPlan) -> None:
        self._sampler = sampler
        self._plan = plan
        self.result_calls = 0
        self.cancel_calls = 0
        self._finished = False

    def result(self) -> SamplerResult:
        self.result_calls += 1
        if self._plan.gate is not None:
            self._plan.gate.wait(timeout=2.0)
        try:
            if isinstance(self._plan.outcome, BaseException):
                raise self._plan.outcome
            return self._plan.outcome
        finally:
            if not self._finished:
                self._finished = True
                with self._sampler.lock:
                    self._sampler.active -= 1

    def cancel(self) -> object:
        self.cancel_calls += 1
        if self._plan.cancel_started is not None:
            self._plan.cancel_started.set()
        if self._plan.gate is not None and self._plan.release_result_on_cancel:
            self._plan.gate.set()
        if self._plan.cancel_gate is not None:
            self._plan.cancel_gate.wait(timeout=2.0)
        if self._plan.cancel_error is not None:
            raise self._plan.cancel_error
        return self._plan.cancel_status


class RecordingSampler:
    def __init__(self, plans: Sequence[ChildPlan]) -> None:
        self.plans = list(plans)
        self.calls: list[dict[str, Any]] = []
        self.children: list[RecordingChildJob] = []
        self.child_created = [threading.Event() for _ in plans]
        self.active = 0
        self.max_active = 0
        self.lock = threading.Lock()

    def run(self, circuits: Sequence[Any], **kwargs: Any) -> RecordingChildJob:
        with self.lock:
            plan = self.plans[len(self.calls)]
            self.calls.append({"circuits": circuits, **kwargs})
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            child = RecordingChildJob(self, plan)
            self.children.append(child)
            self.child_created[len(self.calls) - 1].set()
            return child


class BlockedSubmitChild:
    def __init__(
        self,
        *,
        cancel_status: object = "cancelled",
        cancel_error: BaseException | None = None,
    ) -> None:
        self.cancel_status = cancel_status
        self.cancel_error = cancel_error
        self.cancel_calls = 0

    def result(self) -> SamplerResult:
        raise AssertionError("cancelled child result must not be read")

    def cancel(self) -> object:
        self.cancel_calls += 1
        if self.cancel_error is not None:
            raise self.cancel_error
        return self.cancel_status


class BlockedSubmitSampler:
    def __init__(self, child: BlockedSubmitChild) -> None:
        self.child = child
        self.submit_started = threading.Event()
        self.submit_release = threading.Event()
        self.calls = 0

    def run(self, circuits: Sequence[Any], **kwargs: Any) -> BlockedSubmitChild:
        del circuits, kwargs
        self.calls += 1
        self.submit_started.set()
        assert self.submit_release.wait(timeout=1.0)
        return self.child


class RecordingProgress:
    def __init__(self) -> None:
        self.factory_calls: list[dict[str, Any]] = []
        self.update_calls: list[int] = []
        self.closed = False

    def __call__(self, **kwargs: Any) -> RecordingProgress:
        self.factory_calls.append(kwargs)
        return self

    def __enter__(self) -> RecordingProgress:
        return self

    def __exit__(self, *args: object) -> None:
        self.closed = True

    def update(self, amount: int = 1) -> None:
        self.update_calls.append(amount)


def _record_job_error(
    job: DirectCompositeJob,
    errors: list[BaseException],
) -> None:
    try:
        job.result()
    except BaseException as error:
        errors.append(error)


def _wait_for_child(sampler: RecordingSampler, index: int = 0) -> None:
    assert sampler.child_created[index].wait(timeout=1.0)


@pytest.mark.parametrize(
    ("total_shots", "expected"),
    [
        (1, (1,)),
        (199, (199,)),
        (200, (200,)),
        (201, (200, 1)),
        (2000, (200,) * 10),
        (2050, (200,) * 10 + (50,)),
    ],
)
def test_partition_direct_shots(
    total_shots: int,
    expected: tuple[int, ...],
) -> None:
    assert partition_direct_shots(total_shots) == expected


def test_direct_shot_limit_is_200() -> None:
    assert DIRECT_SHOT_LIMIT == 200


@pytest.mark.parametrize("total_shots", [0, -1, True, 1.5, "200"])
def test_partition_direct_shots_rejects_invalid_total(total_shots: object) -> None:
    with pytest.raises(DirectProviderError, match="positive integer"):
        partition_direct_shots(total_shots)  # type: ignore[arg-type]


def test_exact_counts_reconstructs_integer_counts() -> None:
    result = sampler_result({0: 0.55, 3: 0.45})

    assert exact_counts_from_sampler_result(result, shots=200) == [{0: 110, 3: 90}]


@pytest.mark.parametrize("shots", [0, True, 201])
def test_exact_counts_rejects_invalid_child_shots(shots: object) -> None:
    result = sampler_result({0: 1.0})

    with pytest.raises(DirectProviderError, match="between 1 and 200"):
        exact_counts_from_sampler_result(result, shots=shots)  # type: ignore[arg-type]


def test_aggregate_direct_results_rejects_oversized_child_shots() -> None:
    with pytest.raises(DirectProviderError, match="between 1 and 200"):
        aggregate_direct_results([(sampler_result({0: 1.0}), 201)])


def test_exact_counts_rejects_non_integral_reconstruction() -> None:
    result = sampler_result({0: 0.5, 1: 0.5})

    with pytest.raises(DirectProviderError, match="integer counts"):
        exact_counts_from_sampler_result(result, shots=3)


@pytest.mark.parametrize("state", [1.9, True, -1, "1"])
def test_exact_counts_rejects_non_integral_or_negative_states(state: object) -> None:
    result = SimpleNamespace(quasi_dists=[{state: 1.0}])

    with pytest.raises(DirectProviderError, match="state") as error:
        exact_counts_from_sampler_result(result, shots=200)
    assert str(state) not in str(error.value)


def test_exact_counts_rejects_negative_canonical_integral_state() -> None:
    class NegativeCanonicalState:
        def __index__(self) -> int:
            return -1

        def __int__(self) -> int:
            return -1

        def __lt__(self, other: object) -> bool:
            return False

    Integral.register(NegativeCanonicalState)
    state = NegativeCanonicalState()
    result = SimpleNamespace(quasi_dists=[{state: 1.0}])

    with pytest.raises(DirectProviderError, match="state") as error:
        exact_counts_from_sampler_result(result, shots=200)
    assert "provider payload" not in str(error.value)


@pytest.mark.parametrize("probability", [True, "1.0"])
def test_exact_counts_rejects_non_real_probabilities(probability: object) -> None:
    result = SimpleNamespace(quasi_dists=[{0: probability}])

    with pytest.raises(DirectProviderError, match="probabilities") as error:
        exact_counts_from_sampler_result(result, shots=200)
    assert str(probability) not in str(error.value)


@pytest.mark.parametrize("probability", [float("nan"), float("inf"), float("-inf")])
def test_exact_counts_rejects_non_finite_probabilities(probability: float) -> None:
    result = SimpleNamespace(quasi_dists=[{0: probability}])

    with pytest.raises(DirectProviderError, match="probabilities"):
        exact_counts_from_sampler_result(result, shots=200)


@pytest.mark.parametrize("probability", [-0.1, 1.1])
def test_exact_counts_rejects_probabilities_outside_unit_interval(
    probability: float,
) -> None:
    result = SimpleNamespace(quasi_dists=[{0: probability}])

    with pytest.raises(DirectProviderError, match="between 0 and 1"):
        exact_counts_from_sampler_result(result, shots=200)


def test_exact_counts_rejects_negative_counts() -> None:
    result = sampler_result({0: -0.1, 1: 1.1})

    with pytest.raises(DirectProviderError, match="integer counts"):
        exact_counts_from_sampler_result(result, shots=10)


def test_exact_counts_requires_counts_to_sum_to_shots() -> None:
    result = sampler_result({0: 0.5})

    with pytest.raises(DirectProviderError, match="sum exactly"):
        exact_counts_from_sampler_result(result, shots=10)


def test_aggregate_direct_results_sums_raw_counts() -> None:
    first = sampler_result({0: 0.55, 3: 0.45})
    second = sampler_result({0: 0.60, 3: 0.40})

    result, counts = aggregate_direct_results([(first, 200), (second, 50)])

    assert counts == [{0: 140, 3: 110}]
    assert dict(result.quasi_dists[0]) == {0: 0.56, 3: 0.44}
    assert result.metadata == [{"shots": 250, "cft_piastq_parts": 2}]


def test_aggregate_direct_results_copies_first_child_metadata() -> None:
    first = SamplerResult(
        [QuasiDistribution({0: 1.0})],
        metadata=[{"backend": "direct", "shots": 200}],
    )

    result, _ = aggregate_direct_results(
        [(first, 200), (sampler_result({0: 1.0}), 50)]
    )

    assert result.metadata == [
        {"backend": "direct", "shots": 250, "cft_piastq_parts": 2}
    ]


def test_aggregate_direct_results_deep_copies_first_child_metadata() -> None:
    first = SamplerResult(
        [QuasiDistribution({0: 1.0})],
        metadata=[{"nested": {"labels": ["child"]}}],
    )

    result, _ = aggregate_direct_results([(first, 200)])
    result.metadata[0]["nested"]["labels"].append("aggregate")

    assert first.metadata[0]["nested"] == {"labels": ["child"]}


def test_aggregate_direct_results_ignores_malformed_first_metadata() -> None:
    class MalformedMetadata(Sequence[object]):
        def __len__(self) -> int:
            raise RuntimeError("provider payload")

        def __getitem__(self, index: int) -> object:
            raise RuntimeError("provider payload")

    first = SimpleNamespace(
        quasi_dists=[{0: 1.0}],
        metadata=MalformedMetadata(),
    )

    result, _ = aggregate_direct_results([(first, 200)])

    assert result.metadata == [{"shots": 200, "cft_piastq_parts": 1}]


def test_aggregate_direct_results_preserves_circuit_index_and_order() -> None:
    first = sampler_result({0: 0.75, 1: 0.25}, {0: 0.25, 3: 0.75})
    second = sampler_result({0: 0.5, 1: 0.5}, {0: 0.5, 3: 0.5})

    result, counts = aggregate_direct_results([(first, 200), (second, 100)])

    assert counts == [{0: 200, 1: 100}, {0: 100, 3: 200}]
    assert len(result.quasi_dists) == 2
    assert dict(result.quasi_dists[0]) == {0: 2 / 3, 1: 1 / 3}
    assert dict(result.quasi_dists[1]) == {0: 1 / 3, 3: 2 / 3}


def test_exact_counts_rejects_malformed_quasi_distributions() -> None:
    malformed = object()

    with pytest.raises(DirectProviderError, match="quasi distributions"):
        exact_counts_from_sampler_result(malformed, shots=200)


def test_exact_counts_rejects_empty_quasi_distributions() -> None:
    empty = SimpleNamespace(quasi_dists=[])

    with pytest.raises(DirectProviderError, match="at least one"):
        exact_counts_from_sampler_result(empty, shots=200)


def test_aggregate_direct_results_rejects_empty_child_result() -> None:
    empty = SimpleNamespace(quasi_dists=[], metadata=[])

    with pytest.raises(DirectProviderError, match="at least one"):
        aggregate_direct_results([(empty, 200)])


def test_exact_counts_sanitizes_malformed_probability_error() -> None:
    class MalformedProbability:
        def __float__(self) -> float:
            raise RuntimeError("provider payload")

    malformed = SimpleNamespace(quasi_dists=[{0: MalformedProbability()}])

    with pytest.raises(DirectProviderError, match="integer counts") as error:
        exact_counts_from_sampler_result(malformed, shots=200)
    assert "provider payload" not in str(error.value)


def test_exact_counts_sanitizes_malformed_result_error() -> None:
    class MalformedResult:
        @property
        def quasi_dists(self) -> object:
            raise RuntimeError("provider payload")

    with pytest.raises(DirectProviderError, match="quasi distributions") as error:
        exact_counts_from_sampler_result(MalformedResult(), shots=200)
    assert "provider payload" not in str(error.value)


def test_exact_counts_sanitizes_malformed_distribution_error() -> None:
    class MalformedDistribution(dict[int, float]):
        def items(self) -> object:  # type: ignore[override]
            raise RuntimeError("provider payload")

    malformed = SimpleNamespace(quasi_dists=[MalformedDistribution()])

    with pytest.raises(DirectProviderError, match="integer counts") as error:
        exact_counts_from_sampler_result(malformed, shots=200)
    assert "provider payload" not in str(error.value)


def test_exact_counts_sanitizes_provider_direct_error_from_distribution() -> None:
    class MalformedDistribution(dict[int, float]):
        def items(self) -> object:  # type: ignore[override]
            raise DirectProviderError("provider payload")

    malformed = SimpleNamespace(quasi_dists=[MalformedDistribution()])

    with pytest.raises(DirectProviderError, match="integer counts") as error:
        exact_counts_from_sampler_result(malformed, shots=200)
    assert "provider payload" not in str(error.value)


def test_exact_counts_sanitizes_malformed_sequence_error() -> None:
    class MalformedSequence(Sequence[object]):
        def __len__(self) -> int:
            return 1

        def __getitem__(self, index: int) -> object:
            raise RuntimeError("provider payload")

    malformed = SimpleNamespace(quasi_dists=MalformedSequence())

    with pytest.raises(DirectProviderError, match="quasi distributions") as error:
        exact_counts_from_sampler_result(malformed, shots=200)
    assert "provider payload" not in str(error.value)


def test_exact_counts_sanitizes_hostile_quasi_class_access() -> None:
    malformed = SimpleNamespace(quasi_dists=HostileClassAccess())

    with pytest.raises(DirectProviderError, match="quasi distributions") as error:
        exact_counts_from_sampler_result(malformed, shots=200)
    assert "provider payload" not in str(error.value)


def test_aggregate_direct_results_rejects_changed_circuit_count() -> None:
    first = sampler_result({0: 1.0})
    second = sampler_result({0: 1.0}, {1: 1.0})

    with pytest.raises(DirectProviderError, match="circuit count"):
        aggregate_direct_results([(first, 200), (second, 200)])


def test_aggregate_direct_results_sanitizes_malformed_part_error() -> None:
    class MalformedPart(Sequence[object]):
        def __len__(self) -> int:
            return 2

        def __getitem__(self, index: int) -> object:
            raise RuntimeError("provider payload")

    with pytest.raises(DirectProviderError, match="result and child shots") as error:
        aggregate_direct_results([MalformedPart()])  # type: ignore[list-item]
    assert "provider payload" not in str(error.value)


def test_aggregate_direct_results_sanitizes_malformed_parts_sequence() -> None:
    class MalformedParts(Sequence[tuple[object, int]]):
        def __len__(self) -> int:
            return 1

        def __getitem__(self, index: int) -> tuple[object, int]:
            raise RuntimeError("provider payload")

    with pytest.raises(DirectProviderError, match="result parts") as error:
        aggregate_direct_results(MalformedParts())
    assert "provider payload" not in str(error.value)


def test_aggregate_direct_results_sanitizes_hostile_parts_class_access() -> None:
    with pytest.raises(DirectProviderError, match="result parts") as error:
        aggregate_direct_results(HostileClassAccess())  # type: ignore[arg-type]
    assert "provider payload" not in str(error.value)


def test_composite_job_runs_parts_sequentially_and_caches_exact_result() -> None:
    child_result = sampler_result({0: 1.0})
    sampler = RecordingSampler([ChildPlan(child_result) for _ in range(10)])
    progress = RecordingProgress()
    circuits = [object()]
    parameter_values = [[0.25]]
    provider_options = {"backend": "direct", "optimization_level": 0}
    job = DirectCompositeJob(
        sampler=sampler,
        circuits=circuits,
        parameter_values=parameter_values,
        total_shots=2000,
        provider_options=provider_options,
        progress_factory=progress,
    )

    assert job.job_id().startswith("direct-")
    assert job.status() == "queued"
    assert sampler.calls == []

    result = job.result()

    assert job.status() == "succeeded"
    assert job.result() is result
    assert len(sampler.calls) == 10
    assert sampler.max_active == 1
    assert all(
        call
        == {
            "circuits": circuits,
            "parameter_values": parameter_values,
            "shots": 200,
            "with_progress_bar": False,
            **provider_options,
        }
        for call in sampler.calls
    )
    assert progress.factory_calls == [
        {"total": 10, "desc": "Direct PCSS jobs", "unit": "job"}
    ]
    assert progress.update_calls == [1] * 10
    assert progress.closed
    assert job.counts(num_bits=2) == [{"00": 2000}]


def test_composite_job_failure_stops_later_parts_and_caches_safe_error() -> None:
    provider_error = RuntimeError("provider token=top-secret")
    formatter_calls: list[BaseException] = []

    def formatter(error: BaseException) -> str:
        formatter_calls.append(error)
        return "formatted provider failure"

    sampler = RecordingSampler(
        [
            ChildPlan(sampler_result({0: 1.0})),
            ChildPlan(provider_error),
            ChildPlan(sampler_result({0: 1.0})),
        ]
    )
    progress = RecordingProgress()
    job = DirectCompositeJob(
        sampler=sampler,
        circuits=["circuit"],
        parameter_values=None,
        total_shots=600,
        provider_options={"provider_secret": "raw-option-secret"},
        progress_factory=progress,
        error_formatter=formatter,
    )

    with pytest.raises(DirectProviderError) as first_error:
        job.result()
    with pytest.raises(DirectProviderError) as second_error:
        job.result()
    with pytest.raises(DirectProviderError) as counts_error:
        job.counts()

    assert str(first_error.value) == (
        "Direct PCSS part 2/3 failed: formatted provider failure"
    )
    assert second_error.value is first_error.value
    assert counts_error.value is first_error.value
    assert formatter_calls == [provider_error]
    assert "raw-option-secret" not in str(first_error.value)
    assert len(sampler.calls) == 2
    assert "parameter_values" not in sampler.calls[0]
    assert progress.update_calls == [1]
    assert progress.closed
    assert job.status() == "failed"


def test_composite_job_uses_generic_failure_if_formatter_fails() -> None:
    def broken_formatter(error: BaseException) -> str:
        raise RuntimeError("formatter secret")

    job = DirectCompositeJob(
        sampler=RecordingSampler([ChildPlan(RuntimeError("provider secret"))]),
        circuits=["circuit"],
        parameter_values=None,
        total_shots=200,
        provider_options={},
        error_formatter=broken_formatter,
    )

    with pytest.raises(
        DirectProviderError,
        match=r"^Direct PCSS part 1/1 failed: provider error$",
    ):
        job.result()


def test_composite_job_zero_timeout_starts_no_child_and_is_terminal() -> None:
    sampler = RecordingSampler([ChildPlan(sampler_result({0: 1.0}))])
    job = DirectCompositeJob(
        sampler=sampler,
        circuits=["circuit"],
        parameter_values=None,
        total_shots=200,
        provider_options={},
    )

    with pytest.raises(PiastQTimeoutError) as first_error:
        job.result(timeout=0)
    with pytest.raises(PiastQTimeoutError) as second_error:
        job.result()

    assert second_error.value is first_error.value
    assert sampler.calls == []
    assert job.status() == "failed"


def test_cached_success_precedes_new_zero_timeout() -> None:
    sampler = RecordingSampler([ChildPlan(sampler_result({0: 1.0}))])
    job = DirectCompositeJob(
        sampler=sampler,
        circuits=["circuit"],
        parameter_values=None,
        total_shots=200,
        provider_options={},
    )

    result = job.result()

    assert job.result(timeout=0) is result
    assert job.status() == "succeeded"
    assert len(sampler.calls) == 1


def test_cached_failure_precedes_new_zero_timeout() -> None:
    sampler = RecordingSampler([ChildPlan(RuntimeError("provider failure"))])
    job = DirectCompositeJob(
        sampler=sampler,
        circuits=["circuit"],
        parameter_values=None,
        total_shots=200,
        provider_options={},
    )

    with pytest.raises(DirectProviderError) as first_error:
        job.result()
    with pytest.raises(DirectProviderError) as repeated:
        job.result(timeout=0)

    assert repeated.value is first_error.value
    assert job.status() == "failed"
    assert len(sampler.calls) == 1


def test_composite_job_passes_remaining_deadline_and_stops_when_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ticks = iter([10.0, 10.5, 12.0, 13.0, 16.0])
    monkeypatch.setattr(
        "cft_piastq.direct_composite.time.monotonic", lambda: next(ticks)
    )
    sampler = RecordingSampler(
        [
            ChildPlan(sampler_result({0: 1.0})),
            ChildPlan(sampler_result({0: 1.0})),
        ]
    )
    progress = RecordingProgress()
    job = DirectCompositeJob(
        sampler=sampler,
        circuits=["circuit"],
        parameter_values=None,
        total_shots=400,
        provider_options={},
        progress_factory=progress,
    )

    with pytest.raises(PiastQTimeoutError):
        job.result(timeout=5.0)

    assert len(sampler.calls) == 1
    assert sampler.calls[0]["query_timeout_seconds"] == 3.0
    assert sampler.children[0].result_calls == 1
    assert progress.update_calls == [1]
    assert progress.closed
    assert job.status() == "failed"


def test_composite_job_rejects_final_child_returned_after_logical_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ticks = iter([10.0, 10.1, 10.2, 11.1])
    monkeypatch.setattr(
        "cft_piastq.direct_composite.time.monotonic", lambda: next(ticks)
    )
    sampler = RecordingSampler([ChildPlan(sampler_result({0: 1.0}))])
    job = DirectCompositeJob(
        sampler=sampler,
        circuits=["circuit"],
        parameter_values=None,
        total_shots=200,
        provider_options={},
    )

    with pytest.raises(PiastQTimeoutError) as first_error:
        job.result(timeout=1.0)
    with pytest.raises(PiastQTimeoutError) as second_error:
        job.result()

    assert second_error.value is first_error.value
    assert len(sampler.calls) == 1
    assert job.status() == "failed"


def test_composite_job_rechecks_deadline_after_aggregation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ticks = iter([10.0, 10.1, 10.2, 10.3, 11.1])
    monkeypatch.setattr(
        "cft_piastq.direct_composite.time.monotonic", lambda: next(ticks)
    )
    sampler = RecordingSampler([ChildPlan(sampler_result({0: 1.0}))])
    job = DirectCompositeJob(
        sampler=sampler,
        circuits=["circuit"],
        parameter_values=None,
        total_shots=200,
        provider_options={},
    )

    with pytest.raises(PiastQTimeoutError):
        job.result(timeout=1.0)

    assert len(sampler.calls) == 1
    assert job.status() == "failed"


def test_bounded_job_uses_run_query_timeout_with_primitive_job_result() -> None:
    sampler = RecordingSampler([ChildPlan(sampler_result({0: 1.0}))])
    job = DirectCompositeJob(
        sampler=sampler,
        circuits=["circuit"],
        parameter_values=None,
        total_shots=200,
        provider_options={"query_timeout_seconds": 999.0},
    )

    result = job.result(timeout=5.0)

    query_timeout = sampler.calls[0]["query_timeout_seconds"]
    assert isinstance(query_timeout, float)
    assert 0 < query_timeout <= 5.0
    assert sampler.children[0].result_calls == 1
    assert result is job.result()


def test_unbounded_job_preserves_provider_query_timeout_option() -> None:
    sampler = RecordingSampler([ChildPlan(sampler_result({0: 1.0}))])
    job = DirectCompositeJob(
        sampler=sampler,
        circuits=["circuit"],
        parameter_values=None,
        total_shots=200,
        provider_options={"query_timeout_seconds": 7.5},
    )

    job.result()

    assert sampler.calls[0]["query_timeout_seconds"] == 7.5


@pytest.mark.parametrize(
    "provider_error",
    [TimeoutError("builtin timeout"), type("ProviderTimeoutError", (Exception,), {})()],
)
def test_composite_job_maps_provider_timeout_to_public_timeout(
    provider_error: BaseException,
) -> None:
    job = DirectCompositeJob(
        sampler=RecordingSampler([ChildPlan(provider_error)]),
        circuits=["circuit"],
        parameter_values=None,
        total_shots=400,
        provider_options={},
        show_progress=False,
    )

    with pytest.raises(PiastQTimeoutError, match="Timed out waiting for direct PCSS"):
        job.result(timeout=1.0)
    assert job.status() == "failed"
    assert len(job.sampler.calls) == 1


def test_composite_job_preserves_public_timeout_error() -> None:
    public_error = PiastQTimeoutError("public timeout")
    job = DirectCompositeJob(
        sampler=RecordingSampler([ChildPlan(public_error)]),
        circuits=["circuit"],
        parameter_values=None,
        total_shots=200,
        provider_options={},
    )

    with pytest.raises(PiastQTimeoutError) as raised:
        job.result()

    assert raised.value is public_error


def test_composite_job_propagates_keyboard_interrupt_and_closes_progress() -> None:
    interrupt = KeyboardInterrupt()
    sampler = RecordingSampler(
        [
            ChildPlan(interrupt),
            ChildPlan(sampler_result({0: 1.0})),
        ]
    )
    progress = RecordingProgress()
    job = DirectCompositeJob(
        sampler=sampler,
        circuits=["circuit"],
        parameter_values=None,
        total_shots=400,
        provider_options={},
        progress_factory=progress,
    )

    with pytest.raises(KeyboardInterrupt) as raised:
        job.result()
    with pytest.raises(KeyboardInterrupt) as repeated:
        job.result()

    assert raised.value is interrupt
    assert repeated.value is interrupt
    assert len(sampler.calls) == 1
    assert sampler.active == 0
    assert progress.update_calls == []
    assert progress.closed
    assert job.status() == "failed"


def test_composite_job_pre_cancel_is_terminal_and_starts_no_child() -> None:
    sampler = RecordingSampler([ChildPlan(sampler_result({0: 1.0}))])
    job = DirectCompositeJob(
        sampler=sampler,
        circuits=["circuit"],
        parameter_values=None,
        total_shots=200,
        provider_options={},
    )

    assert job.cancel() == "cancelled"
    with pytest.raises(DirectProviderError, match="cancelled") as first_error:
        job.result()
    with pytest.raises(DirectProviderError) as second_error:
        job.result()

    assert second_error.value is first_error.value
    assert sampler.calls == []
    assert job.status() == "cancelled"


@pytest.mark.parametrize(
    ("cancel_status", "expected_status"),
    [
        ("cancelled", "cancelled"),
        (SimpleNamespace(value="cancelled"), "cancelled"),
        (True, "cancelled"),
        ("running", "cancel_requested"),
    ],
)
def test_composite_job_active_cancel_stops_next_part_and_closes_progress(
    cancel_status: object,
    expected_status: str,
) -> None:
    gate = threading.Event()
    sampler = RecordingSampler(
        [
            ChildPlan(
                sampler_result({0: 1.0}),
                gate=gate,
                cancel_status=cancel_status,
            ),
            ChildPlan(sampler_result({0: 1.0})),
        ]
    )
    progress = RecordingProgress()
    job = DirectCompositeJob(
        sampler=sampler,
        circuits=["circuit"],
        parameter_values=None,
        total_shots=400,
        provider_options={},
        progress_factory=progress,
    )
    errors: list[BaseException] = []

    def execute() -> None:
        try:
            job.result()
        except BaseException as error:
            errors.append(error)

    thread = threading.Thread(target=execute)
    thread.start()
    _wait_for_child(sampler)

    assert job.status() == "running"
    assert job.cancel() == expected_status
    thread.join(timeout=2.0)

    assert not thread.is_alive()
    assert len(errors) == 1
    assert isinstance(errors[0], DirectProviderError)
    assert sampler.children[0].cancel_calls == 1
    assert len(sampler.calls) == 1
    assert job.status() == expected_status
    assert progress.update_calls == []
    assert progress.closed
    with pytest.raises(DirectProviderError) as repeated:
        job.result()
    assert repeated.value is errors[0]


def test_composite_job_cancel_during_final_child_never_becomes_succeeded() -> None:
    gate = threading.Event()
    sampler = RecordingSampler(
        [
            ChildPlan(sampler_result({0: 1.0})),
            ChildPlan(sampler_result({0: 1.0}), gate=gate),
        ]
    )
    progress = RecordingProgress()
    job = DirectCompositeJob(
        sampler=sampler,
        circuits=["circuit"],
        parameter_values=None,
        total_shots=400,
        provider_options={},
        progress_factory=progress,
    )
    errors: list[BaseException] = []

    thread = threading.Thread(target=lambda: _record_job_error(job, errors))
    thread.start()
    _wait_for_child(sampler, index=1)

    assert job.cancel() == "cancelled"
    thread.join(timeout=2.0)

    assert not thread.is_alive()
    assert len(errors) == 1
    assert job.status() == "cancelled"
    assert len(sampler.calls) == 2
    assert progress.update_calls == [1]
    assert progress.closed


def test_composite_job_sanitizes_active_child_cancel_error() -> None:
    gate = threading.Event()
    sampler = RecordingSampler(
        [
            ChildPlan(
                sampler_result({0: 1.0}),
                gate=gate,
                cancel_error=RuntimeError("token=cancel-secret"),
            ),
            ChildPlan(sampler_result({0: 1.0})),
        ]
    )
    progress = RecordingProgress()
    job = DirectCompositeJob(
        sampler=sampler,
        circuits=["circuit"],
        parameter_values=None,
        total_shots=400,
        provider_options={},
        progress_factory=progress,
    )
    result_errors: list[BaseException] = []
    thread = threading.Thread(target=lambda: _record_job_error(job, result_errors))
    thread.start()
    _wait_for_child(sampler)

    with pytest.raises(DirectProviderError) as cancel_error:
        job.cancel()
    gate.set()
    thread.join(timeout=2.0)

    assert "cancel-secret" not in str(cancel_error.value)
    assert "[REDACTED]" in str(cancel_error.value)
    assert len(result_errors) == 1
    assert result_errors[0] is cancel_error.value
    assert len(sampler.calls) == 1
    assert job.status() == "failed"
    assert progress.closed


def test_late_cancel_return_does_not_overwrite_cached_provider_failure() -> None:
    result_gate = threading.Event()
    cancel_started = threading.Event()
    cancel_release = threading.Event()
    sampler = RecordingSampler(
        [
            ChildPlan(
                RuntimeError("provider failure"),
                gate=result_gate,
                cancel_status="cancelled",
                cancel_started=cancel_started,
                cancel_gate=cancel_release,
                release_result_on_cancel=False,
            )
        ]
    )
    job = DirectCompositeJob(
        sampler=sampler,
        circuits=["circuit"],
        parameter_values=None,
        total_shots=200,
        provider_options={},
    )
    result_errors: list[BaseException] = []
    cancel_statuses: list[object] = []

    result_thread = threading.Thread(
        target=lambda: _record_job_error(job, result_errors)
    )
    result_thread.start()
    _wait_for_child(sampler)
    cancel_thread = threading.Thread(
        target=lambda: cancel_statuses.append(job.cancel())
    )
    cancel_thread.start()
    assert cancel_started.wait(timeout=1.0)

    result_gate.set()
    result_thread.join(timeout=2.0)

    assert not result_thread.is_alive()
    assert len(result_errors) == 1
    assert isinstance(result_errors[0], DirectProviderError)
    assert job.status() == "failed"

    cancel_release.set()
    cancel_thread.join(timeout=2.0)

    assert not cancel_thread.is_alive()
    assert cancel_statuses == ["failed"]
    assert job.status() == "failed"
    with pytest.raises(DirectProviderError) as repeated:
        job.result()
    assert repeated.value is result_errors[0]


def test_late_cancel_error_preserves_cached_logical_cancellation() -> None:
    result_gate = threading.Event()
    cancel_started = threading.Event()
    cancel_release = threading.Event()
    sampler = RecordingSampler(
        [
            ChildPlan(
                sampler_result({0: 1.0}),
                gate=result_gate,
                cancel_error=RuntimeError("token=late-cancel-secret"),
                cancel_started=cancel_started,
                cancel_gate=cancel_release,
            )
        ]
    )
    job = DirectCompositeJob(
        sampler=sampler,
        circuits=["circuit"],
        parameter_values=None,
        total_shots=200,
        provider_options={},
    )
    result_errors: list[BaseException] = []
    cancel_errors: list[BaseException] = []

    result_thread = threading.Thread(
        target=lambda: _record_job_error(job, result_errors)
    )
    result_thread.start()
    _wait_for_child(sampler)

    def cancel_job() -> None:
        try:
            job.cancel()
        except BaseException as error:
            cancel_errors.append(error)

    cancel_thread = threading.Thread(target=cancel_job)
    cancel_thread.start()
    assert cancel_started.wait(timeout=1.0)
    result_thread.join(timeout=2.0)

    assert not result_thread.is_alive()
    assert len(result_errors) == 1
    assert isinstance(result_errors[0], DirectProviderError)
    assert job.status() == "cancel_requested"
    with pytest.raises(DirectProviderError) as repeated_before_cancel_return:
        job.result()
    assert repeated_before_cancel_return.value is result_errors[0]

    cancel_release.set()
    cancel_thread.join(timeout=2.0)

    assert not cancel_thread.is_alive()
    assert len(cancel_errors) == 1
    assert isinstance(cancel_errors[0], DirectProviderError)
    assert "late-cancel-secret" not in str(cancel_errors[0])
    assert "[REDACTED]" in str(cancel_errors[0])
    assert job.status() == "cancel_requested"
    with pytest.raises(DirectProviderError) as repeated_after_cancel_return:
        job.result()
    assert repeated_after_cancel_return.value is result_errors[0]


def test_concurrent_cancel_calls_invoke_active_child_cancel_once() -> None:
    result_gate = threading.Event()
    cancel_started = threading.Event()
    cancel_release = threading.Event()
    sampler = RecordingSampler(
        [
            ChildPlan(
                sampler_result({0: 1.0}),
                gate=result_gate,
                cancel_status="cancelled",
                cancel_started=cancel_started,
                cancel_gate=cancel_release,
                release_result_on_cancel=False,
            )
        ]
    )
    job = DirectCompositeJob(
        sampler=sampler,
        circuits=["circuit"],
        parameter_values=None,
        total_shots=200,
        provider_options={},
    )
    result_errors: list[BaseException] = []
    cancel_statuses: list[object] = []
    result_thread = threading.Thread(
        target=lambda: _record_job_error(job, result_errors)
    )
    result_thread.start()
    _wait_for_child(sampler)

    first_cancel = threading.Thread(
        target=lambda: cancel_statuses.append(job.cancel())
    )
    second_cancel = threading.Thread(
        target=lambda: cancel_statuses.append(job.cancel())
    )
    first_cancel.start()
    assert cancel_started.wait(timeout=1.0)
    second_cancel.start()
    cancel_release.set()
    first_cancel.join(timeout=2.0)
    second_cancel.join(timeout=2.0)

    assert not first_cancel.is_alive()
    assert not second_cancel.is_alive()
    assert sampler.children[0].cancel_calls == 1
    assert cancel_statuses == ["cancelled", "cancelled"]

    result_gate.set()
    result_thread.join(timeout=2.0)
    assert not result_thread.is_alive()
    assert len(result_errors) == 1
    assert job.status() == "cancelled"


def test_post_submit_cancel_race_reuses_public_cancel_attempt() -> None:
    post_submit_entered = threading.Event()
    post_submit_release = threading.Event()
    race_path_started = threading.Event()
    cancel_started = threading.Event()
    cancel_release = threading.Event()
    sampler = RecordingSampler(
        [
            ChildPlan(
                sampler_result({0: 1.0}),
                cancel_status="cancelled",
                cancel_started=cancel_started,
                cancel_gate=cancel_release,
            )
        ]
    )
    job = DirectCompositeJob(
        sampler=sampler,
        circuits=["circuit"],
        parameter_values=None,
        total_shots=200,
        provider_options={},
    )
    original_post_submit = job._raise_if_cancelled_after_submit

    def gated_post_submit(child: object) -> None:
        post_submit_entered.set()
        assert post_submit_release.wait(timeout=1.0)
        race_path_started.set()
        original_post_submit(child)

    job._raise_if_cancelled_after_submit = gated_post_submit  # type: ignore[method-assign]
    result_errors: list[BaseException] = []
    cancel_statuses: list[object] = []
    result_thread = threading.Thread(
        target=lambda: _record_job_error(job, result_errors)
    )
    result_thread.start()
    assert post_submit_entered.wait(timeout=1.0)
    cancel_thread = threading.Thread(
        target=lambda: cancel_statuses.append(job.cancel())
    )
    cancel_thread.start()
    assert cancel_started.wait(timeout=1.0)

    post_submit_release.set()
    assert race_path_started.wait(timeout=1.0)
    assert sampler.children[0].cancel_calls == 1
    cancel_release.set()
    cancel_thread.join(timeout=2.0)
    result_thread.join(timeout=2.0)

    assert not cancel_thread.is_alive()
    assert not result_thread.is_alive()
    assert sampler.children[0].cancel_calls == 1
    assert cancel_statuses == ["cancelled"]
    assert len(result_errors) == 1


def test_pre_active_cancel_confirmation_refines_status_after_submit() -> None:
    child = BlockedSubmitChild(cancel_status="cancelled")
    sampler = BlockedSubmitSampler(child)
    job = DirectCompositeJob(
        sampler=sampler,
        circuits=["circuit"],
        parameter_values=None,
        total_shots=200,
        provider_options={},
    )
    result_errors: list[BaseException] = []
    result_thread = threading.Thread(
        target=lambda: _record_job_error(job, result_errors)
    )

    result_thread.start()
    assert sampler.submit_started.wait(timeout=1.0)
    assert job.cancel() == "cancel_requested"
    sampler.submit_release.set()
    result_thread.join(timeout=2.0)

    assert not result_thread.is_alive()
    assert len(result_errors) == 1
    assert isinstance(result_errors[0], DirectProviderError)
    assert job.status() == "cancelled"
    assert child.cancel_calls == 1
    with pytest.raises(DirectProviderError) as repeated:
        job.result()
    assert repeated.value is result_errors[0]


def test_pre_active_internal_cancel_error_replaces_provisional_marker() -> None:
    child = BlockedSubmitChild(
        cancel_error=RuntimeError("token=post-submit-cancel-secret")
    )
    sampler = BlockedSubmitSampler(child)
    job = DirectCompositeJob(
        sampler=sampler,
        circuits=["circuit"],
        parameter_values=None,
        total_shots=200,
        provider_options={},
    )
    result_errors: list[BaseException] = []
    result_thread = threading.Thread(
        target=lambda: _record_job_error(job, result_errors)
    )

    result_thread.start()
    assert sampler.submit_started.wait(timeout=1.0)
    assert job.cancel() == "cancel_requested"
    sampler.submit_release.set()
    result_thread.join(timeout=2.0)

    assert not result_thread.is_alive()
    assert len(result_errors) == 1
    error = result_errors[0]
    assert isinstance(error, DirectProviderError)
    assert "Direct PCSS cancellation failed" in str(error)
    assert "post-submit-cancel-secret" not in str(error)
    assert "[REDACTED]" in str(error)
    assert job.status() == "failed"
    assert child.cancel_calls == 1
    with pytest.raises(DirectProviderError) as repeated:
        job.result()
    assert repeated.value is error


def test_late_confirmed_cancel_refines_logical_cancellation_status() -> None:
    result_gate = threading.Event()
    cancel_started = threading.Event()
    cancel_release = threading.Event()
    sampler = RecordingSampler(
        [
            ChildPlan(
                sampler_result({0: 1.0}),
                gate=result_gate,
                cancel_status="cancelled",
                cancel_started=cancel_started,
                cancel_gate=cancel_release,
            )
        ]
    )
    job = DirectCompositeJob(
        sampler=sampler,
        circuits=["circuit"],
        parameter_values=None,
        total_shots=200,
        provider_options={},
    )
    result_errors: list[BaseException] = []
    cancel_statuses: list[object] = []
    result_thread = threading.Thread(
        target=lambda: _record_job_error(job, result_errors)
    )
    result_thread.start()
    _wait_for_child(sampler)
    cancel_thread = threading.Thread(
        target=lambda: cancel_statuses.append(job.cancel())
    )
    cancel_thread.start()
    assert cancel_started.wait(timeout=1.0)
    result_thread.join(timeout=2.0)

    assert not result_thread.is_alive()
    assert len(result_errors) == 1
    assert job.status() == "cancel_requested"
    with pytest.raises(DirectProviderError) as before_confirmation:
        job.result()
    assert before_confirmation.value is result_errors[0]

    cancel_release.set()
    cancel_thread.join(timeout=2.0)

    assert not cancel_thread.is_alive()
    assert cancel_statuses == ["cancelled"]
    assert job.status() == "cancelled"
    with pytest.raises(DirectProviderError) as after_confirmation:
        job.result()
    assert after_confirmation.value is result_errors[0]


@pytest.mark.parametrize(
    ("total_shots", "show_progress"),
    [(200, True), (400, False)],
)
def test_composite_job_skips_progress_factory_when_not_needed(
    total_shots: int,
    show_progress: bool,
) -> None:
    sampler = RecordingSampler(
        [ChildPlan(sampler_result({0: 1.0})) for _ in range(total_shots // 200)]
    )
    progress = RecordingProgress()
    job = DirectCompositeJob(
        sampler=sampler,
        circuits=["circuit"],
        parameter_values=None,
        total_shots=total_shots,
        provider_options={},
        show_progress=show_progress,
        progress_factory=progress,
    )

    job.result()

    assert progress.factory_calls == []


def test_composite_job_concurrent_result_calls_share_one_execution() -> None:
    gate = threading.Event()
    sampler = RecordingSampler(
        [ChildPlan(sampler_result({0: 1.0}), gate=gate)]
    )
    job = DirectCompositeJob(
        sampler=sampler,
        circuits=["circuit"],
        parameter_values=None,
        total_shots=200,
        provider_options={},
    )
    results: list[SamplerResult] = []

    first = threading.Thread(target=lambda: results.append(job.result()))
    second = threading.Thread(target=lambda: results.append(job.result()))
    first.start()
    _wait_for_child(sampler)
    second.start()
    gate.set()
    first.join(timeout=2.0)
    second.join(timeout=2.0)

    assert len(results) == 2
    assert results[0] is results[1]
    assert len(sampler.calls) == 1


def test_concurrent_result_timeout_does_not_fail_active_logical_execution() -> None:
    gate = threading.Event()
    sampler = RecordingSampler(
        [ChildPlan(sampler_result({0: 1.0}), gate=gate)]
    )
    job = DirectCompositeJob(
        sampler=sampler,
        circuits=["circuit"],
        parameter_values=None,
        total_shots=200,
        provider_options={},
    )
    first_results: list[SamplerResult] = []
    first_errors: list[BaseException] = []
    waiter_errors: list[BaseException] = []

    def execute_first() -> None:
        try:
            first_results.append(job.result())
        except BaseException as error:
            first_errors.append(error)

    def execute_waiter() -> None:
        try:
            job.result(timeout=0.02)
        except BaseException as error:
            waiter_errors.append(error)

    first = threading.Thread(target=execute_first)
    first.start()
    _wait_for_child(sampler)
    waiter = threading.Thread(target=execute_waiter)
    waiter.start()
    waiter.join(timeout=0.5)

    assert not waiter.is_alive()
    assert len(waiter_errors) == 1
    assert isinstance(waiter_errors[0], PiastQTimeoutError)
    assert first.is_alive()
    assert job.status() == "running"
    assert len(sampler.calls) == 1

    gate.set()
    first.join(timeout=2.0)

    assert not first.is_alive()
    assert first_errors == []
    assert len(first_results) == 1
    assert job.status() == "succeeded"
    assert job.result() is first_results[0]
    assert len(sampler.calls) == 1


def test_composite_job_validates_malformed_first_part_before_next_submission() -> None:
    malformed = sampler_result({0: 0.5})
    sampler = RecordingSampler(
        [ChildPlan(malformed)]
        + [ChildPlan(sampler_result({0: 1.0})) for _ in range(9)]
    )
    progress = RecordingProgress()
    job = DirectCompositeJob(
        sampler=sampler,
        circuits=["circuit"],
        parameter_values=None,
        total_shots=2000,
        provider_options={},
        progress_factory=progress,
    )

    with pytest.raises(DirectProviderError) as raised:
        job.result()

    assert str(raised.value).startswith("Direct PCSS part 1/10 failed:")
    assert "sum exactly" in str(raised.value)
    assert len(sampler.calls) == 1
    assert progress.update_calls == []
    assert progress.closed
    assert job.status() == "failed"


def test_composite_job_rejects_child_with_wrong_submitted_circuit_count() -> None:
    sampler = RecordingSampler(
        [
            ChildPlan(sampler_result({0: 1.0})),
            ChildPlan(sampler_result({0: 1.0})),
        ]
    )
    job = DirectCompositeJob(
        sampler=sampler,
        circuits=["first", "second"],
        parameter_values=None,
        total_shots=400,
        provider_options={},
        show_progress=False,
    )

    with pytest.raises(DirectProviderError) as raised:
        job.result()

    assert str(raised.value).startswith("Direct PCSS part 1/2 failed:")
    assert "circuit count" in str(raised.value)
    assert len(sampler.calls) == 1
    assert job.status() == "failed"


def test_composite_job_formats_exact_counts_for_multiple_circuits() -> None:
    sampler = RecordingSampler(
        [ChildPlan(sampler_result({0: 0.5, 3: 0.5}, {1: 1.0}))]
    )
    job = DirectCompositeJob(
        sampler=sampler,
        circuits=["first", "second"],
        parameter_values=None,
        total_shots=200,
        provider_options={},
    )

    assert job.counts() == [{"00": 100, "11": 100}, {"01": 200}]
    assert job.counts(num_bits=3) == [
        {"000": 100, "011": 100},
        {"001": 200},
    ]
