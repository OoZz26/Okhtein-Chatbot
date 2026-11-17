"""The one place that knows what a product link looks like. Links come from handles, never from the model."""


def product_url(store_url: str, handle: str) -> str:
    return f"{store_url.rstrip('/')}/products/{handle}"
