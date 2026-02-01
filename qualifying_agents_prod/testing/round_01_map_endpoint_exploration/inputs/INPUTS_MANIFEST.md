# Round 01 - Input Dependencies

## Target Domains
We will test the `/map` endpoint on the following domains to validate its ability to find key pages (pricing, about, team).

- **Source**: Manual list
- **Domains**:
  - `stripe.com` (Complex B2B, many pages)
  - `linear.app` (Modern SaaS)
  - `openai.com` (High traffic, complex structure)
  - `vercel.com` (Developer tool)

## Environment Variables
- `FIRECRAWL_API_KEY`: Required for authentication.
