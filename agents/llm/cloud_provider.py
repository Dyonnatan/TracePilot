import os

from openai import OpenAI

from .base import LLMProvider

DEFAULT_MODEL = "openai/gpt-4o-mini"


class CloudProvider(LLMProvider):
    """Provider via OpenRouter (API compatível com a da OpenAI).

    OpenRouter dá acesso a um catálogo amplo de modelos (baratos e caros)
    atrás de uma única chave e uma única API — por isso é o backend cloud
    padrão do TracePilot. Para trocar de modelo (ex.: sair de um modelo
    pequeno/barato de teste para um mais avançado), basta mudar
    `OPENROUTER_MODEL` no `.env`; não é preciso alterar este código.

    Catálogo de modelos: https://openrouter.ai/models
    """

    def __init__(self, model: str | None = None):
        self.model = model or os.getenv("OPENROUTER_MODEL", DEFAULT_MODEL)
        self._api_key = os.getenv("OPENROUTER_API_KEY")
        self._client: OpenAI | None = None

    def _get_client(self) -> OpenAI:
        if self._client is None:
            if not self._api_key:
                raise RuntimeError(
                    "OPENROUTER_API_KEY não configurada. Copie .env.example "
                    "para .env e preencha com sua chave da OpenRouter."
                )
            self._client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=self._api_key,
                default_headers={
                    "HTTP-Referer": os.getenv(
                        "OPENROUTER_SITE_URL", "https://github.com/Dyonnatan/TracePilot"
                    ),
                    "X-Title": "TracePilot",
                },
            )
        return self._client

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

        response = self._get_client().chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            **kwargs,
        )
        return response.choices[0].message.content or ""
