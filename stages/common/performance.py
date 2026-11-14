from dataclasses import dataclass


@dataclass(frozen=True)
class Workload:
    id: str
    clients: int
    path: str
    size: int
    persistent: bool = False
    tls: bool = False
    gzip: bool = False
    rounds: int = 5
    warmup_seconds: float = 1.0
    seconds: float = 3.0
    timeout_seconds: float = 2.0


def matrix(modes):
    return [Workload(f'{mode}-{size}-{clients}', clients,
                     prefix + str(size) + ('.txt' if zipped else ''),
                     size, persistent, tls, zipped)
            for clients in (256, 4096)
            for mode, persistent, tls, zipped, prefix in modes
            for size in (4096, 65536)]
