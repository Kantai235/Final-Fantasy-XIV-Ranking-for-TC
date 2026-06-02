/**
 * 公開資料契約集中在這裡，原因是前端、SEO 建置與資料管線都會讀同一批 JSON。
 * 新增欄位時請先更新這份契約，再調整產生器與前端讀取端，避免網站讀到半套欄位。
 *
 * @typedef {Object} RankingEntry
 * @property {string} id
 * @property {string} character_name
 * @property {string} server
 * @property {string} job
 * @property {number} dps
 * @property {number} rdps
 * @property {number} adps
 * @property {number} clear_time_seconds
 * @property {string} recorded_at_iso
 * @property {string} report_code
 * @property {string} report_url
 * @property {number} fight_id
 * @property {number} rank
 *
 * @typedef {Object} UserProfile
 * @property {1} schema_version
 * @property {string} character_name
 * @property {string|null} canonical_server
 * @property {Array<UserEncounter>} encounters
 *
 * @typedef {Object} UserEncounter
 * @property {string} encounter_key
 * @property {RankingEntry|null} best_entry
 * @property {Array<RankingEntry>} public_entries
 *
 * @typedef {Object} UserEntryDetailsPayload
 * @property {1} schema_version
 * @property {"user_entry_details_v1"} format
 * @property {Record<string, { report_variants: Array<object>, source_reports: Array<string> }>} entries
 *
 * @typedef {Object} TeamRankingsPayload
 * @property {1} schema_version
 * @property {Array<TeamEncounter>} encounters
 *
 * @typedef {Object} TeamEncounter
 * @property {string} encounter_key
 * @property {Array<TeamRecord>} records
 *
 * @typedef {Object} TeamRecord
 * @property {string} id
 * @property {Array<TeamPlayer>} players
 *
 * @typedef {Object} TeamPlayer
 * @property {string} character_name
 * @property {string} server
 * @property {string} job
 *
 * @typedef {Object} ServerComparePayload
 * @property {1} schema_version
 * @property {Array<ServerCompareRow>} servers
 *
 * @typedef {Object} ServerCompareRow
 * @property {string} server
 * @property {Array<ServerEncounterCompareRow>} encounters
 */

const typeLabelByName = {
  array: "陣列",
  boolean: "布林值",
  integer: "整數",
  null: "null",
  number: "數字",
  object: "物件",
  string: "字串",
};

function field(type, options = {}) {
  return { type, ...options };
}

function optional(schema) {
  return { ...schema, optional: true };
}

function nullable(schema) {
  return { ...schema, nullable: true };
}

function arrayOf(items, options = {}) {
  return field("array", { items, ...options });
}

function recordOf(values, options = {}) {
  return field("object", { values, additionalProperties: true, ...options });
}

function objectOf(properties, options = {}) {
  return field("object", {
    properties,
    additionalProperties: false,
    ...options,
  });
}

const stringSchema = field("string");
const numberSchema = field("number");
const integerSchema = field("integer");
const booleanSchema = field("boolean");
const isoTimestampSchema = field("string", { format: "iso-date-time" });
const dataPathSchema = field("string", { format: "data-path" });
const urlSchema = field("string", { format: "url" });
const nullableStringSchema = nullable(stringSchema);
const nullableNumberSchema = nullable(numberSchema);
const nullableIsoTimestampSchema = nullable(isoTimestampSchema);
const nullableUrlSchema = nullable(urlSchema);

const versionStatusSchema = field("string", { enum: ["valid", "obsolete"] });
const nullableVersionStatusSchema = nullable(versionStatusSchema);

const versionCutoffSchema = objectOf({
  patch: optional(stringSchema),
  obsolete_after_iso: isoTimestampSchema,
  obsolete_after_local: optional(stringSchema),
  timezone: optional(stringSchema),
  valid_label: optional(stringSchema),
  obsolete_label: optional(stringSchema),
});

const hiddenReportFields = {
  report_hidden: optional(booleanSchema),
  hidden_reason: optional(nullableStringSchema),
  hidden_detected_at_iso: optional(nullableIsoTimestampSchema),
  hidden_source: optional(nullableStringSchema),
};

const gcdCoverageSchema = nullable(objectOf({
  percent: numberSchema,
  covered_time_ms: optional(numberSchema),
  denominator_ms: optional(numberSchema),
  downtime_ms: optional(numberSchema),
  gcd_cast_count: optional(numberSchema),
  calculation_version: integerSchema,
  source: stringSchema,
  xivanalysis_url: optional(urlSchema),
  speed_stat_source: optional(stringSchema),
  coverage_downtime_ms: optional(numberSchema),
  denominator_downtime_ms: optional(numberSchema),
  estimated_speed_below_minimum: optional(booleanSchema),
  fallback_selection: optional(stringSchema),
  downtime_selection: optional(stringSchema),
  raw_events_percent: optional(nullableNumberSchema),
  raw_events_denominator_ms: optional(nullableNumberSchema),
  casts_graph_percent: optional(nullableNumberSchema),
  casts_graph_denominator_ms: optional(nullableNumberSchema),
  raw_targetability_percent: optional(nullableNumberSchema),
  raw_targetability_denominator_ms: optional(nullableNumberSchema),
  raw_next_gcd_capped_percent: optional(nullableNumberSchema),
  raw_next_gcd_capped_denominator_ms: optional(nullableNumberSchema),
}));

const gcdCoverageStatusSchema = objectOf({
  state: stringSchema,
  calculation_version: optional(integerSchema),
  checked_at_iso: optional(isoTimestampSchema),
  reason: optional(stringSchema),
  source: optional(stringSchema),
  fallback_from: optional(stringSchema),
});

const performanceSchema = objectOf({
  qualified: booleanSchema,
  active_threshold: numberSchema,
  sample_count: integerSchema,
  reason: optional(stringSchema),
  rank: optional(integerSchema),
  top_percent: optional(numberSchema),
  score_percentile: optional(numberSchema),
  median_rdps: optional(numberSchema),
  q3_rdps: optional(numberSchema),
  top10_rdps: optional(numberSchema),
  delta_to_median: optional(nullableNumberSchema),
  delta_to_q3: optional(nullableNumberSchema),
  gap_to_top10: optional(nullableNumberSchema),
});

const reportVariantSchema = objectOf({
  key: stringSchema,
  report_code: nullableStringSchema,
  report_url: nullableUrlSchema,
  report_title: nullableStringSchema,
  fight_id: nullableNumberSchema,
  recorded_at: nullableNumberSchema,
  recorded_at_iso: nullableIsoTimestampSchema,
  dps: nullableNumberSchema,
  rdps: nullableNumberSchema,
  adps: nullableNumberSchema,
  ndps: nullableNumberSchema,
  total_damage: nullableNumberSchema,
  active_time_ms: nullableNumberSchema,
  active_percent: nullableNumberSchema,
  clear_time_ms: nullableNumberSchema,
  clear_time_seconds: nullableNumberSchema,
  damage_downtime_ms: nullableNumberSchema,
  damage_downtime_seconds: nullableNumberSchema,
  damage_time_ms: nullableNumberSchema,
  damage_time_seconds: nullableNumberSchema,
  fflogs_source_id: optional(numberSchema),
  gcd_coverage: optional(gcdCoverageSchema),
  gcd_coverage_status: optional(gcdCoverageStatusSchema),
  ...hiddenReportFields,
});

const compactReportVariantSchema = objectOf({
  key: stringSchema,
  report_code: optional(nullableStringSchema),
  report_url: optional(nullableUrlSchema),
  report_title: optional(nullableStringSchema),
  fight_id: optional(nullableNumberSchema),
  recorded_at: optional(nullableNumberSchema),
  recorded_at_iso: optional(nullableIsoTimestampSchema),
  dps: optional(nullableNumberSchema),
  rdps: optional(nullableNumberSchema),
  adps: optional(nullableNumberSchema),
  ndps: optional(nullableNumberSchema),
  total_damage: optional(nullableNumberSchema),
  active_time_ms: optional(nullableNumberSchema),
  active_percent: optional(nullableNumberSchema),
  clear_time_ms: optional(nullableNumberSchema),
  clear_time_seconds: optional(nullableNumberSchema),
  damage_downtime_ms: optional(nullableNumberSchema),
  damage_downtime_seconds: optional(nullableNumberSchema),
  damage_time_ms: optional(nullableNumberSchema),
  damage_time_seconds: optional(nullableNumberSchema),
  fflogs_source_id: optional(numberSchema),
  gcd_coverage: optional(gcdCoverageSchema),
  gcd_coverage_status: optional(gcdCoverageStatusSchema),
  ...Object.fromEntries(Object.entries(hiddenReportFields).map(([key, schema]) => [key, optional(schema)])),
});

const rankingEntrySchema = objectOf({
  id: stringSchema,
  character_name: stringSchema,
  server: stringSchema,
  job: stringSchema,
  dps: numberSchema,
  rdps: numberSchema,
  adps: numberSchema,
  ndps: optional(numberSchema),
  total_damage: optional(numberSchema),
  active_time_ms: numberSchema,
  active_percent: numberSchema,
  gcd_coverage: optional(gcdCoverageSchema),
  gcd_coverage_status: optional(gcdCoverageStatusSchema),
  clear_time_ms: numberSchema,
  clear_time_seconds: numberSchema,
  damage_downtime_ms: nullableNumberSchema,
  damage_downtime_seconds: nullableNumberSchema,
  damage_time_ms: nullableNumberSchema,
  damage_time_seconds: nullableNumberSchema,
  recorded_at_iso: isoTimestampSchema,
  report_code: stringSchema,
  report_url: urlSchema,
  fight_id: numberSchema,
  fflogs_source_id: optional(numberSchema),
  duplicate_count: numberSchema,
  rank: numberSchema,
  is_obsolete_record: optional(booleanSchema),
  version_status: optional(versionStatusSchema),
  version_cutoff_iso: optional(isoTimestampSchema),
  ...hiddenReportFields,
});

const fullEntrySchema = objectOf({
  id: stringSchema,
  encounter_key: stringSchema,
  encounter_name: stringSchema,
  encounter_category: nullableStringSchema,
  character_name: stringSchema,
  server: stringSchema,
  job: stringSchema,
  dps: numberSchema,
  rdps: numberSchema,
  adps: numberSchema,
  ndps: optional(numberSchema),
  total_damage: optional(numberSchema),
  active_time_ms: numberSchema,
  active_percent: numberSchema,
  gcd_coverage: optional(gcdCoverageSchema),
  gcd_coverage_status: optional(gcdCoverageStatusSchema),
  clear_time_ms: numberSchema,
  clear_time_seconds: numberSchema,
  damage_downtime_ms: nullableNumberSchema,
  damage_downtime_seconds: nullableNumberSchema,
  damage_time_ms: nullableNumberSchema,
  damage_time_seconds: nullableNumberSchema,
  recorded_at: nullableNumberSchema,
  recorded_at_iso: isoTimestampSchema,
  report_code: stringSchema,
  report_url: urlSchema,
  fflogs_source_id: optional(numberSchema),
  report_title: nullableStringSchema,
  fight_id: nullableNumberSchema,
  rank: nullableNumberSchema,
  job_rank: nullableNumberSchema,
  overall_rank: nullableNumberSchema,
  duplicate_count: numberSchema,
  performance: optional(performanceSchema),
  report_variants: optional(arrayOf(reportVariantSchema)),
  source_reports: optional(arrayOf(stringSchema)),
  report_detail_path: optional(dataPathSchema),
  report_detail_id: optional(stringSchema),
  is_obsolete_record: optional(booleanSchema),
  version_status: optional(versionStatusSchema),
  version_cutoff_iso: optional(isoTimestampSchema),
  ...hiddenReportFields,
});

const entrySummarySchema = objectOf({
  id: stringSchema,
  encounter_key: stringSchema,
  encounter_name: stringSchema,
  encounter_category: nullableStringSchema,
  character_name: stringSchema,
  server: stringSchema,
  job: stringSchema,
  dps: numberSchema,
  rdps: numberSchema,
  adps: numberSchema,
  active_percent: nullableNumberSchema,
  gcd_coverage: optional(gcdCoverageSchema),
  gcd_coverage_status: optional(gcdCoverageStatusSchema),
  clear_time_seconds: nullableNumberSchema,
  recorded_at_iso: nullableIsoTimestampSchema,
  report_code: nullableStringSchema,
  report_url: nullableUrlSchema,
  fflogs_source_id: optional(numberSchema),
  rank: nullableNumberSchema,
  job_rank: nullableNumberSchema,
  performance: nullable(performanceSchema),
  is_obsolete_record: booleanSchema,
  version_status: nullableVersionStatusSchema,
  version_cutoff_iso: nullableIsoTimestampSchema,
});

const rankingPayloadSchema = objectOf({
  schema_version: field("integer", { const: 1 }),
  encounter: objectOf({}, { additionalProperties: true }),
  updated_at: optional(nullableNumberSchema),
  updated_at_iso: nullableIsoTimestampSchema,
  hidden_reports_included: booleanSchema,
  ranking_entries: arrayOf(rankingEntrySchema),
  version_cutoff: optional(versionCutoffSchema),
  version_ranking_entries: optional(objectOf({
    all: arrayOf(rankingEntrySchema),
    valid: arrayOf(rankingEntrySchema),
    obsolete: arrayOf(rankingEntrySchema),
  })),
});

const rankingHiddenDeltaPayloadSchema = objectOf({
  schema_version: field("integer", { const: 1 }),
  format: field("string", { const: "ranking_hidden_delta_v1" }),
  base_path: dataPathSchema,
  encounter: objectOf({}, { additionalProperties: true }),
  updated_at: optional(nullableNumberSchema),
  updated_at_iso: nullableIsoTimestampSchema,
  hidden_reports_included: field("boolean", { const: true }),
  ranking_entry_order: arrayOf(stringSchema),
  ranking_entries: arrayOf(rankingEntrySchema),
  version_cutoff: optional(versionCutoffSchema),
  version_ranking_entry_order: optional(objectOf({
    all: arrayOf(stringSchema),
    valid: arrayOf(stringSchema),
    obsolete: arrayOf(stringSchema),
  })),
  version_ranking_entries: optional(objectOf({
    all: arrayOf(rankingEntrySchema),
    valid: arrayOf(rankingEntrySchema),
    obsolete: arrayOf(rankingEntrySchema),
  })),
});

const rankingDetailsPayloadSchema = objectOf({
  schema_version: field("integer", { const: 1 }),
  format: field("string", { const: "ranking_detail_entries_v1" }),
  encounter: objectOf({}, { additionalProperties: true }),
  updated_at: optional(nullableNumberSchema),
  updated_at_iso: nullableIsoTimestampSchema,
  hidden_reports_included: booleanSchema,
  entries: recordOf(rankingEntrySchema),
});

const rankingDetailsHiddenDeltaPayloadSchema = objectOf({
  schema_version: field("integer", { const: 1 }),
  format: field("string", { const: "ranking_detail_hidden_delta_v1" }),
  base_path: dataPathSchema,
  encounter: objectOf({}, { additionalProperties: true }),
  updated_at: optional(nullableNumberSchema),
  updated_at_iso: nullableIsoTimestampSchema,
  hidden_reports_included: field("boolean", { const: true }),
  entries: recordOf(rankingEntrySchema),
});

const userIndexEntrySchema = objectOf({
  character_name: stringSchema,
  canonical_server: nullableStringSchema,
  servers: arrayOf(stringSchema),
  server_aliases: arrayOf(stringSchema),
  file_path: dataPathSchema,
  encounter_count: integerSchema,
  public_entry_count: integerSchema,
  best_rdps: nullableNumberSchema,
  profile_job: nullableStringSchema,
  profile_job_rank: nullableNumberSchema,
  last_recorded_at_iso: nullableIsoTimestampSchema,
});

const teammateEncounterSchema = objectOf({
  encounter_key: stringSchema,
  encounter_name: stringSchema,
  co_clear_count: integerSchema,
});

const teammateUserServerSchema = objectOf({
  server: stringSchema,
  co_clear_count: integerSchema,
});

const frequentTeammateSchema = objectOf({
  character_name: stringSchema,
  server: stringSchema,
  jobs: arrayOf(stringSchema),
  co_clear_count: integerSchema,
  last_recorded_at_iso: nullableIsoTimestampSchema,
  user_servers: arrayOf(teammateUserServerSchema),
  encounters: arrayOf(teammateEncounterSchema),
});

const userEncounterSchema = objectOf({
  encounter_key: stringSchema,
  encounter_name: stringSchema,
  encounter_category: nullableStringSchema,
  updated_at_iso: nullableIsoTimestampSchema,
  best_entry: nullable(fullEntrySchema),
  best_by_job: arrayOf(fullEntrySchema),
  public_entries: arrayOf(fullEntrySchema),
});

const userProfileSchema = objectOf({
  schema_version: field("integer", { const: 1 }),
  generated_at_iso: isoTimestampSchema,
  character_name: stringSchema,
  canonical_server: nullableStringSchema,
  servers: arrayOf(stringSchema),
  server_aliases: arrayOf(stringSchema),
  summary: objectOf({
    encounter_count: integerSchema,
    public_entry_count: integerSchema,
    teammate_count: integerSchema,
    best_rdps: nullableNumberSchema,
    best_encounter_key: nullableStringSchema,
    profile_job: nullableStringSchema,
    profile_encounter_key: nullableStringSchema,
    profile_job_rank: nullableNumberSchema,
    last_recorded_at_iso: nullableIsoTimestampSchema,
  }),
  frequent_teammates: arrayOf(frequentTeammateSchema),
  encounters: arrayOf(userEncounterSchema),
});

const userHiddenDeltaEncounterSchema = objectOf({
  encounter_key: stringSchema,
  encounter_name: stringSchema,
  encounter_category: nullableStringSchema,
  updated_at_iso: nullableIsoTimestampSchema,
  best_entry: nullable(fullEntrySchema),
  best_by_job: arrayOf(fullEntrySchema),
  public_entry_order: arrayOf(stringSchema),
  public_entries: arrayOf(fullEntrySchema),
});

const userProfileHiddenDeltaSchema = objectOf({
  schema_version: field("integer", { const: 1 }),
  format: field("string", { const: "user_profile_hidden_delta_v1" }),
  base_path: dataPathSchema,
  generated_at_iso: isoTimestampSchema,
  character_name: stringSchema,
  canonical_server: nullableStringSchema,
  servers: arrayOf(stringSchema),
  server_aliases: arrayOf(stringSchema),
  summary: objectOf({
    encounter_count: integerSchema,
    public_entry_count: integerSchema,
    teammate_count: integerSchema,
    best_rdps: nullableNumberSchema,
    best_encounter_key: nullableStringSchema,
    profile_job: nullableStringSchema,
    profile_encounter_key: nullableStringSchema,
    profile_job_rank: nullableNumberSchema,
    last_recorded_at_iso: nullableIsoTimestampSchema,
  }),
  frequent_teammates: arrayOf(frequentTeammateSchema),
  encounter_order: arrayOf(stringSchema),
  encounters: arrayOf(userHiddenDeltaEncounterSchema),
});

const userEntryReportDetailSchema = objectOf({
  duplicate_count: integerSchema,
  source_reports: arrayOf(stringSchema),
  report_variants: arrayOf(compactReportVariantSchema),
});

const userEntryDetailsPayloadSchema = objectOf({
  schema_version: field("integer", { const: 1 }),
  format: field("string", { const: "user_entry_details_v1" }),
  generated_at_iso: isoTimestampSchema,
  character_name: stringSchema,
  canonical_server: nullableStringSchema,
  hidden_reports_included: booleanSchema,
  entry_count: integerSchema,
  entries: recordOf(userEntryReportDetailSchema),
});

const userIndexPayloadSchema = objectOf({
  schema_version: field("integer", { const: 1 }),
  generated_at_iso: isoTimestampSchema,
  rankings_updated_at_iso: nullableIsoTimestampSchema,
  total_users: integerSchema,
  users: arrayOf(userIndexEntrySchema),
});

const teamPlayerSchema = objectOf({
  character_name: stringSchema,
  server: stringSchema,
  job: stringSchema,
  role: stringSchema,
  role_name: stringSchema,
  dps: numberSchema,
  rdps: numberSchema,
  adps: nullableNumberSchema,
  active_percent: nullableNumberSchema,
  fflogs_source_id: optional(numberSchema),
  gcd_coverage: optional(gcdCoverageSchema),
  gcd_coverage_status: optional(gcdCoverageStatusSchema),
});

const teamRecordSchema = objectOf({
  id: stringSchema,
  encounter_key: stringSchema,
  encounter_name: stringSchema,
  encounter_category: nullableStringSchema,
  clear_time_seconds: numberSchema,
  clear_time_ms: nullableNumberSchema,
  recorded_at_iso: nullableIsoTimestampSchema,
  report_code: stringSchema,
  report_url: urlSchema,
  fight_id: nullableNumberSchema,
  duplicate_count: integerSchema,
  total_rdps: numberSchema,
  total_adps: numberSchema,
  total_dps: numberSchema,
  players: arrayOf(teamPlayerSchema),
  rank: optional(integerSchema),
  is_obsolete_record: optional(booleanSchema),
  version_status: optional(versionStatusSchema),
  version_cutoff_iso: optional(isoTimestampSchema),
  ...hiddenReportFields,
});

const teamEncounterSliceSchema = objectOf({
  encounter_key: stringSchema,
  encounter_name: stringSchema,
  encounter_category: nullableStringSchema,
  record_count: integerSchema,
  fastest_clear_seconds: nullableNumberSchema,
  fastest_record: nullable(teamRecordSchema),
  records: arrayOf(teamRecordSchema),
  version_mode: field("string", { enum: ["all", "valid", "obsolete"] }),
});

const teamEncounterSchema = objectOf({
  encounter_key: stringSchema,
  encounter_name: stringSchema,
  encounter_category: nullableStringSchema,
  record_count: integerSchema,
  fastest_clear_seconds: nullableNumberSchema,
  fastest_record: nullable(teamRecordSchema),
  records: arrayOf(teamRecordSchema),
  version_cutoff: optional(objectOf({
    obsolete_after_iso: isoTimestampSchema,
  })),
  version_slices: optional(objectOf({
    all: teamEncounterSliceSchema,
    valid: teamEncounterSliceSchema,
    obsolete: teamEncounterSliceSchema,
  })),
});

const teamRankingsPayloadSchema = objectOf({
  schema_version: field("integer", { const: 1 }),
  generated_at_iso: isoTimestampSchema,
  rankings_updated_at_iso: nullableIsoTimestampSchema,
  total_team_record_count: integerSchema,
  encounter_count: integerSchema,
  overall_fastest: arrayOf(teamRecordSchema),
  encounters: arrayOf(teamEncounterSchema),
});

const distributionRoleSchema = objectOf({
  role: stringSchema,
  role_name: stringSchema,
  clear_count: integerSchema,
  entry_count: integerSchema,
  percentage: numberSchema,
});

const distributionJobSchema = objectOf({
  job: stringSchema,
  clear_count: integerSchema,
  entry_count: integerSchema,
  percentage: numberSchema,
  role: stringSchema,
  role_name: stringSchema,
});

const damageMetricSchema = objectOf({
  count: integerSchema,
  min: numberSchema,
  q1: numberSchema,
  median: numberSchema,
  q3: numberSchema,
  max: numberSchema,
  average: numberSchema,
});

const damageProfileSchema = objectOf({
  dps: nullable(damageMetricSchema),
  rdps: nullable(damageMetricSchema),
  adps: nullable(damageMetricSchema),
});

const jobDamageStatsSchema = objectOf({
  job: stringSchema,
  role: stringSchema,
  role_name: stringSchema,
  entry_count: integerSchema,
  metrics: damageProfileSchema,
});

const serverEncounterCompareRowSchema = objectOf({
  encounter_key: stringSchema,
  encounter_name: stringSchema,
  encounter_category: nullableStringSchema,
  character_count: integerSchema,
  job_record_count: integerSchema,
  entry_count: integerSchema,
  clear_share_percent: numberSchema,
  damage_profile: damageProfileSchema,
  best_entry: nullable(entrySummarySchema),
  fastest_entry: nullable(entrySummarySchema),
});

const serverCompareRowSchema = objectOf({
  server: stringSchema,
  unique_player_count: integerSchema,
  encounter_clear_count: integerSchema,
  role_record_count: integerSchema,
  job_record_count: integerSchema,
  entry_count: integerSchema,
  encounter_count: integerSchema,
  role_stats: arrayOf(distributionRoleSchema),
  job_stats: arrayOf(distributionJobSchema),
  damage_stats: arrayOf(jobDamageStatsSchema),
  rdps_stats: nullable(damageMetricSchema),
  best_entry: nullable(entrySummarySchema),
  fastest_entry: nullable(entrySummarySchema),
  encounters: arrayOf(serverEncounterCompareRowSchema),
});

const serverComparePayloadSchema = objectOf({
  schema_version: field("integer", { const: 1 }),
  generated_at_iso: isoTimestampSchema,
  rankings_updated_at_iso: nullableIsoTimestampSchema,
  summary: objectOf({
    server_count: integerSchema,
    top_clear_server: nullable(field("object", { additionalProperties: true })),
    top_rdps_server: nullable(field("object", { additionalProperties: true })),
    fastest_server: nullable(field("object", { additionalProperties: true })),
  }),
  servers: arrayOf(serverCompareRowSchema),
});

function valueType(value) {
  if (value === null) {
    return "null";
  }
  if (Array.isArray(value)) {
    return "array";
  }
  if (typeof value === "number" && Number.isInteger(value)) {
    return "integer";
  }
  return typeof value;
}

function checkFormat(value, schema, label, issues) {
  if (schema.format === "iso-date-time" && Number.isNaN(new Date(value).getTime())) {
    issues.push(`${label} 必須是有效 ISO 時間字串`);
  }
  if (schema.format === "url") {
    try {
      const url = new URL(value);
      if (!["http:", "https:"].includes(url.protocol)) {
        issues.push(`${label} 必須是 http 或 https URL`);
      }
    } catch {
      issues.push(`${label} 必須是有效 URL`);
    }
  }
  if (schema.format === "data-path" && !value.startsWith("data/")) {
    issues.push(`${label} 必須是 data/ 開頭的公開資料路徑`);
  }
}

function validateNode(value, schema, label, issues) {
  if (schema.nullable && value === null) {
    return;
  }

  if (schema.const !== undefined && value !== schema.const) {
    issues.push(`${label} 必須固定為 ${JSON.stringify(schema.const)}`);
    return;
  }

  if (schema.enum && !schema.enum.includes(value)) {
    issues.push(`${label} 必須是 ${schema.enum.map((item) => JSON.stringify(item)).join("、")} 其中之一`);
    return;
  }

  const actualType = valueType(value);
  const matchesType = schema.type === "number"
    ? actualType === "number" || actualType === "integer"
    : actualType === schema.type;

  if (!matchesType) {
    issues.push(`${label} 必須是 ${typeLabelByName[schema.type] || schema.type}，目前是 ${typeLabelByName[actualType] || actualType}`);
    return;
  }

  if (schema.type === "number" && !Number.isFinite(value)) {
    issues.push(`${label} 必須是有限數字`);
    return;
  }

  checkFormat(value, schema, label, issues);

  if (schema.type === "array" && schema.items) {
    value.forEach((item, index) => validateNode(item, schema.items, `${label}[${index}]`, issues));
  }

  if (schema.type !== "object" || value === null || Array.isArray(value)) {
    return;
  }

  const properties = schema.properties || {};
  for (const [propertyName, propertySchema] of Object.entries(properties)) {
    if (!Object.hasOwn(value, propertyName)) {
      if (!propertySchema.optional) {
        issues.push(`${label}.${propertyName} 是必要欄位`);
      }
      continue;
    }
    validateNode(value[propertyName], propertySchema, `${label}.${propertyName}`, issues);
  }

  if (schema.values) {
    for (const [key, childValue] of Object.entries(value)) {
      validateNode(childValue, schema.values, `${label}.${key}`, issues);
    }
    return;
  }

  if (schema.additionalProperties === false) {
    for (const key of Object.keys(value)) {
      if (!Object.hasOwn(properties, key)) {
        issues.push(`${label}.${key} 不在公開資料契約中`);
      }
    }
  }
}

export function validateSchemaContract(value, schema, label) {
  const issues = [];
  validateNode(value, schema, label, issues);
  return issues;
}

export const publicDataContracts = {
  rankingEntry: rankingEntrySchema,
  rankingPayload: rankingPayloadSchema,
  rankingHiddenDeltaPayload: rankingHiddenDeltaPayloadSchema,
  rankingDetailsPayload: rankingDetailsPayloadSchema,
  rankingDetailsHiddenDeltaPayload: rankingDetailsHiddenDeltaPayloadSchema,
  userIndexPayload: userIndexPayloadSchema,
  userProfile: userProfileSchema,
  userProfileHiddenDelta: userProfileHiddenDeltaSchema,
  userEntryDetailsPayload: userEntryDetailsPayloadSchema,
  teamRankingsPayload: teamRankingsPayloadSchema,
  serverComparePayload: serverComparePayloadSchema,
};
