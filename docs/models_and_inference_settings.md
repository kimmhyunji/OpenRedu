# Models, inference settings, and missing provenance

## Table R2. Models, inference settings, and missing provenance

| Stage | Recorded model identifier | Settings and provenance |
|---|---|---|
| Primary extraction | us.anthropic.claude-haiku-4-5-20251001-v1:0 | AWS Bedrock; maximum 400 output tokens; temperature and top-p unset (provider defaults); per-case attempts, token use, and latency not retained for the original pass |
| Diagnosis–caption consistency check (within Verification) | us.anthropic.claude-haiku-4-5-20251001-v1:0 | Maximum 100 output tokens; first 500 caption characters; sampling parameters not explicitly set |
| Middle extraction tier | mistral.mistral-large-3-675b-instruct | Extraction model fallback configuration; maximum 400 output tokens; sampling parameters not explicitly set |
| Escalated extraction | us.anthropic.claude-sonnet-4-6 | Extraction model fallback and forced retry; maximum 400 output tokens; sampling parameters not explicitly set |
| Figure-scoped finding rewrite | us.anthropic.claude-haiku-4-5-20251001-v1:0 | Temperature 0; maximum 600 output tokens; two extra attempts for output-format failure and up to 14 throttle retries; finding-rewrite fallback threshold 0.5 (figure-evidence lexical overlap) |
| Independent verifier | us.amazon.nova-pro-v1:0 | AWS Bedrock, us-east-1; temperature 0; maximum 3,000 output tokens; model, settings, prompt, timestamp, tokens, duration, and raw response logged |
| Topic suggestion (Tracking agent) | us.anthropic.claude-haiku-4-5-20251001-v1:0 | AWS Bedrock; maximum 800 output tokens; up to 30 not-yet-viewed topics supplied and up to 10 returned; temperature and top-p unset (provider defaults) |
| Development verifier comparators | openai.gpt-oss-120b-1:0; deepseek.v3.2 | Temperature 0; maximum 3,000 output tokens; gpt-oss reasoning effort low; development comparison only, results not reported |
| Incomplete development comparator | us.meta.llama4-maverick-17b-instruct-v1:0 | Request-throttled run; not a completed comparator |
