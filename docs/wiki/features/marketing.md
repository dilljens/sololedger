# Marketing

Generate changelog, blog posts, and social media content from git history using any LLM API (OpenAI, Anthropic, or local).

## Key Functions

- `app.marketing.MarketingGenerator` — generates marketing content from git history
- CLI: `llc marketing blog` (blog post draft), `llc marketing social` (social media posts)

## Configuration

- Provider auto-detected from `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`, or `LLM_PROVIDER=local` for local models
