// SynapseCME graph schema — loaded into Neo4j at bootstrap.
// Hierarchy: Region -> Country -> City -> Facility -> Equipment
// Facts: Observation -> Equipment, Observation -> Contributor
// Parameters: Parameter -> Equipment (measurements inferred from observations)
// State consensus: Desconocido -> Estimado -> Reportado -> Confirmado

CREATE CONSTRAINT region_name IF NOT EXISTS FOR (r:Region) REQUIRE r.name IS UNIQUE;
CREATE CONSTRAINT country_name IF NOT EXISTS FOR (c:Country) REQUIRE c.name IS UNIQUE;
CREATE CONSTRAINT city_name IF NOT EXISTS FOR (c:City) REQUIRE c.name IS UNIQUE;
CREATE CONSTRAINT facility_id IF NOT EXISTS FOR (f:Facility) REQUIRE f.id IS UNIQUE;
CREATE CONSTRAINT equipment_id IF NOT EXISTS FOR (e:Equipment) REQUIRE e.id IS UNIQUE;
CREATE CONSTRAINT observation_id IF NOT EXISTS FOR (o:Observation) REQUIRE o.id IS UNIQUE;
CREATE CONSTRAINT contributor_name IF NOT EXISTS FOR (c:Contributor) REQUIRE c.name IS UNIQUE;
CREATE CONSTRAINT parameter_id IF NOT EXISTS FOR (p:Parameter) REQUIRE p.id IS UNIQUE;

// Full-text search over facility and equipment names for matching.
CREATE FULLTEXT INDEX facilitySearch IF NOT EXISTS FOR (f:Facility) ON EACH [f.name];
CREATE FULLTEXT INDEX equipmentSearch IF NOT EXISTS FOR (e:Equipment) ON EACH [e.modality, e.manufacturer, e.model];
