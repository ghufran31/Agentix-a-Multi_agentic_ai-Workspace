FROM pgvector/pgvector:0.8.7-pg17-bookworm
COPY --chmod=755 init-agentix.sh /docker-entrypoint-initdb.d/10-agentix.sh
RUN sed -i 's/\r$//' /docker-entrypoint-initdb.d/10-agentix.sh
