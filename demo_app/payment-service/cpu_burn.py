"""Processos que consomem CPU dentro do container (cenário cpu_saturation).

Módulo sem dependências da aplicação: é importado pelos processos filhos
criados com o start method "spawn".
"""
import multiprocessing


def _burn() -> None:
    while True:
        pass


class CpuBurner:
    def __init__(self) -> None:
        self._context = multiprocessing.get_context("spawn")
        self._processes: list[multiprocessing.Process] = []

    @property
    def workers(self) -> int:
        return sum(1 for process in self._processes if process.is_alive())

    def start(self, workers: int) -> None:
        self.stop()
        for _ in range(workers):
            process = self._context.Process(target=_burn, daemon=True)
            process.start()
            self._processes.append(process)

    def stop(self) -> None:
        for process in self._processes:
            process.terminate()
        for process in self._processes:
            process.join(timeout=5)
        self._processes = []
