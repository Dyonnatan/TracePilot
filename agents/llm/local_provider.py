import os

import ollama

from .base import LLMProvider

DEFAULT_MODEL = "llama3.2:3b"


class LocalProvider(LLMProvider):
    """Provider via modelo open-weight local, servido pelo Ollama.

    Pensado para GPUs de entrada (ex.: 4GB de VRAM): o padrão é um modelo
    pequeno (`llama3.2:3b`, ~2GB em q4) que roda inteiro na GPU. Modelos
    maiores (ex. `qwen2.5:7b-instruct`) também funcionam — o Ollama faz
    offload parcial pra CPU se não couber na VRAM, só fica mais lento.
    Trocar de modelo é só mudar `OLLAMA_MODEL` no `.env`.
    """

    def __init__(self, model: str | None = None):
        self.host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self.model = model or os.getenv("OLLAMA_MODEL", DEFAULT_MODEL)
        self._client = ollama.Client(host=self.host)

    def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.2,
        **kwargs,
    ) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        try:
            response = self._client.chat(
                model=self.model,
                messages=messages,
                options={"temperature": temperature},
            )
        except Exception as exc:
            raise RuntimeError(
                f"Falha ao chamar o Ollama em {self.host} com o modelo "
                f"'{self.model}'. Confirme que o serviço está rodando "
                f"(`ollama serve`) e que o modelo foi baixado "
                f"(`ollama pull {self.model}`)."
            ) from exc

        return response["message"]["content"] or ""
