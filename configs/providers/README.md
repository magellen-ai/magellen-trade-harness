# Providers

A provider describes one model service connection. It may expose multiple models.

```yaml
protocol: openai-compatible
base_url: "$EXAMPLE_BASE_URL"
api_key_env: "$EXAMPLE_API_KEY"
models:
  - model-a
  - model-b
```

Agent declarations refer to a model as `provider-id/model-name` through
`model.provider` + `model.name`. Materialized instances keep the legacy bare
`model` field for harness compatibility and add `model_provider` and
`model_ref` with the canonical value. Provider files must not contain API keys.
