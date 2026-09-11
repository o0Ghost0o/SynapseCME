"""SynapseCME Application Knowledge Base for Agent Context."""

APP_KNOWLEDGE_BASE = """
About SynapseCME:
- SynapseCME is a decentralized, agent-first intelligence platform for hospital medical equipment.
- It transforms unstructured field observations (text, audio, photo evidence) into a live GraphRAG knowledge graph in Neo4j with local on-edge inference (QVAC / MedPsy) and PostgreSQL audit logs.

Consensus States and Lifecycle:
- Equipment and attributes progress through consensus based on independent observer votes:
  * "Desconocido" (Unknown): No observations or evidence recorded yet (0 votes).
  * "Estimado" (Estimated): Has observations, but the cumulative confidence weight is less than 1.0 (a preliminary note or a single uncorroborated observation).
  * "Reportado" (Reported): Cumulative confidence weight >= 1.0 from a single contributor.
  * "Confirmado" (Confirmed): Cumulative confidence weight >= 1.0 corroborated by at least 2 distinct independent contributors.
- When a user asks why an equipment is in state "Estimado", explain clearly that it has an initial field observation whose cumulative confidence weight has not yet reached the 1.0 threshold, or that it has not yet been corroborated by a second independent contributor.

Technical Magnitudes & Parameters:
- Monitored: voltage (voltaje), current (corriente), helium level (nivel de helio), temperature (temperatura), pressure (presión), tube scans (cortes de tubo), dose rate (tasa de dosis), etc.
- Inferred status: "ok" (nominal, normal), "warning" (advertencia, fluctuante, alto/bajo), "critical" (crítico, fuera de rango, falla).

Platform Capabilities:
- Fast field capture with voice dictation (STT) and optional photo evidence.
- Full offline mode with persistent local queue, auto-sync when online, and transactional multi-message batching.
- Non-destructive Q&A: When asked questions or explanations (e.g. why a state was set, what a parameter means, what SynapseCME is), answer conversationally in Spanish using the knowledge base and current equipment data. NEVER invent, modify, or delete equipment or parameters during Q&A.
"""
