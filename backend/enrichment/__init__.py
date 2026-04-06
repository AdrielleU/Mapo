"""
Pluggable enrichment system for Mapo.

Usage::

    from backend.enrichment import get_provider
    provider = get_provider()
    data = provider.enrich("https://example.com")
"""
from backend.config import config
from backend.enrichment.base import EnrichmentProvider
from backend.enrichment.email_quality import classify_email, analyze_emails


_PROVIDERS: dict[str, str] = {
    "rapidapi": "backend.enrichment.rapidapi.RapidAPIProvider",
    "hunter": "backend.enrichment.hunter.HunterIOProvider",
    "apollo": "backend.enrichment.apollo.ApolloProvider",
}


def get_provider(name: str | None = None, **kwargs) -> EnrichmentProvider:
    """
    Return an enrichment provider instance based on config or *name* override.

    Args:
        name: Provider name (``"rapidapi"``, ``"hunter"``, ``"apollo"``).
              Defaults to ``config.enrichment.provider``.
        **kwargs: Extra keyword arguments forwarded to the provider constructor
                  (e.g. ``api_key``).
    """
    provider_name = (name or config.enrichment.provider).lower()

    dotted_path = _PROVIDERS.get(provider_name)
    if dotted_path is None:
        raise ValueError(
            f"Unknown enrichment provider {provider_name!r}. "
            f"Available: {', '.join(sorted(_PROVIDERS))}"
        )

    module_path, class_name = dotted_path.rsplit(".", 1)

    import importlib
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)

    return cls(**kwargs)
