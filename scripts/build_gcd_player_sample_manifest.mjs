import fs from 'node:fs'
import path from 'node:path'

const DEFAULT_SOURCE_MANIFEST = 'docs/gcd_xivanalysis_player_sample_completion_manifest_v2094.json'
const DEFAULT_OUTPUT_PATH = 'docs/gcd_xivanalysis_player_sample_completion_manifest_latest.json'
const EVIDENCE_PATTERN = /^gcd_xivanalysis_(audit|recompute)_player_sample.*\.json$/u

function parseArgs(argv) {
  const args = {
    sourceManifest: DEFAULT_SOURCE_MANIFEST,
    outputPath: DEFAULT_OUTPUT_PATH,
    docsDir: 'docs',
  }
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index]
    if (arg === '--source-manifest') {
      args.sourceManifest = argv.at(++index)
    } else if (arg === '--output-path') {
      args.outputPath = argv.at(++index)
    } else if (arg === '--docs-dir') {
      args.docsDir = argv.at(++index)
    } else {
      throw new Error(`未知參數：${arg}`)
    }
  }
  return args
}

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, 'utf8'))
}

function writeJson(filePath, data) {
  fs.mkdirSync(path.dirname(filePath), {recursive: true})
  fs.writeFileSync(filePath, `${JSON.stringify(data, null, 2)}\n`)
}

function evidenceKind(fileName) {
  return fileName.startsWith('gcd_xivanalysis_recompute_') ? 'recompute' : 'audit'
}

function iterEvidenceFiles(docsDir) {
  return fs.readdirSync(docsDir)
    .filter((name) => EVIDENCE_PATTERN.test(name))
    .map((name) => path.join(docsDir, name).replaceAll(path.sep, '/'))
    .sort((left, right) => left.localeCompare(right))
}

function stateOf(player) {
  return String(player?.state ?? player?.status ?? '')
}

function rowEncounterKey(fight, player) {
  return String(player?.encounter_key ?? fight?.encounter_key ?? '')
}

function rowReportCode(fight, player) {
  return String(player?.report_code ?? fight?.report_code ?? '')
}

function rowFightId(fight, player) {
  return Number(player?.fight_id ?? fight?.fight_id ?? fight?.fightId)
}

function rowSourceId(player) {
  return Number(player?.fflogs_id ?? player?.source_id ?? player?.sourceID)
}

function rowJob(player) {
  return String(player?.job ?? '')
}

function matchedKey(fight, player) {
  return [
    rowEncounterKey(fight, player),
    rowReportCode(fight, player),
    rowFightId(fight, player),
    rowSourceId(player),
    rowJob(player),
  ].join('|')
}

function comboKey(encounterKey, job) {
  return `${encounterKey}||${job}`
}

function emptyEvidence(filePath) {
  return {
    file: filePath,
    kind: evidenceKind(path.basename(filePath)),
    matchedKeys: new Set(),
    mismatched: 0,
    errors: 0,
    skipped: 0,
    total: 0,
  }
}

function scanEvidenceFile(filePath) {
  let report
  try {
    report = readJson(filePath)
  } catch {
    return []
  }
  if (!Array.isArray(report?.fights)) {
    return []
  }

  const byCombo = new Map()
  for (const fight of report.fights) {
    if (!fight || typeof fight !== 'object' || !Array.isArray(fight.players)) {
      continue
    }
    for (const player of fight.players) {
      if (!player || typeof player !== 'object') {
        continue
      }
      const encounterKey = rowEncounterKey(fight, player)
      const job = rowJob(player)
      if (!encounterKey || !job) {
        continue
      }

      const key = comboKey(encounterKey, job)
      let evidence = byCombo.get(key)
      if (!evidence) {
        evidence = emptyEvidence(filePath)
        evidence.encounterKey = encounterKey
        evidence.job = job
        byCombo.set(key, evidence)
      }

      evidence.total += 1
      const state = stateOf(player)
      if (state === 'matched') {
        evidence.matchedKeys.add(matchedKey(fight, player))
      } else if (state === 'mismatched' || state === 'mismatch') {
        evidence.mismatched += 1
      } else if (state.startsWith('skipped')) {
        evidence.skipped += 1
      } else {
        evidence.errors += 1
      }
    }
  }

  return Array.from(byCombo.values())
}

function evidenceRank(evidence) {
  return [
    evidence.errors,
    -evidence.matchedKeys.size,
    evidence.file.includes('_cache_') ? 0 : 1,
    evidence.file,
  ]
}

function compareRank(left, right) {
  const leftRank = evidenceRank(left)
  const rightRank = evidenceRank(right)
  for (let index = 0; index < leftRank.length; index += 1) {
    if (leftRank[index] < rightRank[index]) {
      return -1
    }
    if (leftRank[index] > rightRank[index]) {
      return 1
    }
  }
  return 0
}

function selectEvidence(evidences) {
  const clean = evidences.filter((item) => item.mismatched === 0 && item.matchedKeys.size > 0)
  const completeSingle = clean
    .filter((item) => item.matchedKeys.size >= 100)
    .sort(compareRank)
  if (completeSingle.length > 0) {
    return {
      files: [completeSingle[0]],
      matchedKeys: new Set(completeSingle[0].matchedKeys),
    }
  }

  const selectedFiles = []
  const matchedKeys = new Set()
  for (const evidence of clean.sort(compareRank)) {
    const before = matchedKeys.size
    for (const key of evidence.matchedKeys) {
      matchedKeys.add(key)
    }
    if (matchedKeys.size > before) {
      selectedFiles.push(evidence)
    }
    if (matchedKeys.size >= 100) {
      break
    }
  }

  return {files: selectedFiles, matchedKeys}
}

function legacyEntry(entry) {
  return {
    encounter_key: entry.encounter_key,
    job: entry.job,
    status: entry.status,
    matched: entry.matched ?? 0,
    mismatched: entry.mismatched ?? 0,
    errors: entry.errors ?? 0,
    total: entry.total ?? 0,
    evidence_file: entry.evidence_file ?? null,
    evidence_kind: entry.evidence_kind ?? null,
    summary: entry.summary,
    covers_100_auditable_players: Boolean(entry.covers_100_auditable_players),
  }
}

function buildManifest(args) {
  const sourceManifest = readJson(args.sourceManifest)
  const expectedEntries = Array.isArray(sourceManifest.entries) ? sourceManifest.entries : []
  const evidencesByCombo = new Map()

  for (const filePath of iterEvidenceFiles(args.docsDir)) {
    for (const evidence of scanEvidenceFile(filePath)) {
      const key = comboKey(evidence.encounterKey, evidence.job)
      const list = evidencesByCombo.get(key) ?? []
      list.push(evidence)
      evidencesByCombo.set(key, list)
    }
  }

  const entries = expectedEntries.map((entry) => {
    const key = comboKey(entry.encounter_key, entry.job)
    const selected = selectEvidence(evidencesByCombo.get(key) ?? [])
    const matched = selected.matchedKeys.size
    if (matched >= 100) {
      const errors = selected.files.reduce((sum, evidence) => sum + evidence.errors, 0)
      const total = selected.files.reduce((sum, evidence) => sum + evidence.total, 0)
      const evidenceFiles = selected.files.map((evidence) => evidence.file)
      const evidenceKinds = [...new Set(selected.files.map((evidence) => evidence.kind))]
      return {
        encounter_key: entry.encounter_key,
        job: entry.job,
        status: 'complete',
        matched,
        mismatched: 0,
        errors,
        total,
        evidence_file: evidenceFiles[0] ?? null,
        evidence_files: evidenceFiles,
        evidence_kind: evidenceKinds.length === 1 ? evidenceKinds[0] : 'aggregate',
        evidence_kinds: evidenceKinds,
        covers_100_auditable_players: true,
      }
    }

    const legacy = legacyEntry(entry)
    if (legacy.status === 'complete') {
      return legacy
    }
    if (matched > 0) {
      const errors = selected.files.reduce((sum, evidence) => sum + evidence.errors, 0)
      const total = selected.files.reduce((sum, evidence) => sum + evidence.total, 0)
      return {
        encounter_key: entry.encounter_key,
        job: entry.job,
        status: 'incomplete',
        matched,
        mismatched: 0,
        errors,
        total,
        evidence_file: selected.files[0]?.file ?? null,
        evidence_files: selected.files.map((evidence) => evidence.file),
        evidence_kind: selected.files.length > 1 ? 'aggregate' : selected.files[0]?.kind ?? null,
        covers_100_auditable_players: false,
      }
    }
    return legacy
  })

  const summary = {
    schema_version: 2,
    generated_at_iso: new Date().toISOString(),
    source_manifest: args.sourceManifest,
    scope: 'player-sample 每副本每職業 100 位玩家；優先選擇單一完整證據，必要時聚合多份 mismatched=0 的快取或重算證據，以 unique report/fight/sourceID/job matched>=100 視為目前可稽核完成。',
    encounter_count: sourceManifest.summary?.encounter_count ?? new Set(entries.map((entry) => entry.encounter_key)).size,
    job_count: sourceManifest.summary?.job_count ?? new Set(entries.map((entry) => entry.job)).size,
    expected_combo_count: entries.length,
    complete_combo_count: entries.filter((entry) => entry.status === 'complete').length,
    incomplete_combo_count: entries.filter((entry) => entry.status === 'incomplete').length,
    missing_combo_count: entries.filter((entry) => entry.status === 'missing').length,
    total_matched_in_selected_evidence: entries.reduce((sum, entry) => sum + (entry.matched ?? 0), 0),
    total_mismatched_in_selected_evidence: entries.reduce((sum, entry) => sum + (entry.mismatched ?? 0), 0),
    total_errors_in_selected_evidence: entries.reduce((sum, entry) => sum + (entry.errors ?? 0), 0),
  }

  return {
    summary,
    incomplete: entries.filter((entry) => entry.status === 'incomplete'),
    missing_combos: entries
      .filter((entry) => entry.status === 'missing')
      .map((entry) => ({encounter_key: entry.encounter_key, job: entry.job})),
    entries,
  }
}

const args = parseArgs(process.argv.slice(2))
const manifest = buildManifest(args)
writeJson(args.outputPath, manifest)
console.log(`已寫出 player-sample 完成度 manifest：${args.outputPath}`)
console.log(JSON.stringify(manifest.summary, null, 2))
