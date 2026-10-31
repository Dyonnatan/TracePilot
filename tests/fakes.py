"""Substitutos dos providers e do cliente de telemetria.

Nenhum método abre rede, carrega modelo ou lê credencial.
"""


class FakeLLM:
    def __init__(self, replies=None):
        self.replies = list(replies or [])
        self.prompts = []
        self.systems = []

    def generate(self, prompt, **kwargs):
        self.prompts.append(prompt)
        self.systems.append(kwargs.get("system"))
        if not self.replies:
            return "ok"
        return self.replies.pop(0)


class FakeOpenObserve:
    def __init__(self, logs=None, traces=None, metrics=None, logs_error=None, traces_error=None, metrics_error=None):
        self.logs = list(logs or [])
        self.traces = list(traces or [])
        self.metrics = list(metrics or [])
        self.logs_error = logs_error
        self.traces_error = traces_error
        self.metrics_error = metrics_error
        self.queries = []

    def query_logs(self, **kwargs):
        self.queries.append(("logs", kwargs))
        if self.logs_error:
            raise self.logs_error
        return list(self.logs)

    def query_traces(self, **kwargs):
        self.queries.append(("traces", kwargs))
        if self.traces_error:
            raise self.traces_error
        return list(self.traces)

    def query_metrics(self, **kwargs):
        self.queries.append(("metrics", kwargs))
        if self.metrics_error:
            raise self.metrics_error
        return list(self.metrics)


class FakeDecision:
    def __init__(self, value=0.81, error=None):
        self.value = value
        self.error = error
        self.calls = []

    def yes_no(self, state_text, instructions, key="decision"):
        self.calls.append((state_text, instructions, key))
        if self.error:
            raise self.error
        return self.value
