from __future__ import annotations

import os

from qiskit import QuantumCircuit

from cft_piastq import PiastQClient, PiastQSampler


def build_bell_circuit() -> QuantumCircuit:
    circuit = QuantumCircuit(2, 2, name="bell")
    circuit.h(0)
    circuit.cx(0, 1)
    circuit.measure([0, 1], [0, 1])
    return circuit


def main() -> None:
    client = PiastQClient(
        mode="direct",
        owner=os.environ.get("USER", "local-user"),
        token=os.environ["PCSS_TOKEN"],
    )
    sampler = PiastQSampler(
        client.backend,
        options={"cft_job_name": "direct-bell"},
    )

    job = sampler.run(build_bell_circuit(), shots=1024)
    print(job.counts()[0])


if __name__ == "__main__":
    main()
