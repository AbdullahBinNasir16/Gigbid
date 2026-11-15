The custom application services have individual Dockerfiles. The web, worker,
and MCP services remain disabled in Compose until their entry points are ready.
Database, cache, vector store, local model, object store, and tracing services
use their upstream images.

Copy `.env.example` to `.env` and set every required secret before starting
Compose. The API and Langfuse use separate databases in the shared PostgreSQL
service. Raw datasets and local credentials are excluded from the Docker build
context.
