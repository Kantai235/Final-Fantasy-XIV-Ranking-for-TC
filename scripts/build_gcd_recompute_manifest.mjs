import { mkdir, readdir, readFile, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const ROOT_DIR = path.resolve(__dirname, '..')
const DEFAULT_SOURCE_MANIFEST = 'docs/gcd_xivanalysis_top_rankings_completion_manifest_v1908.json'
const DEFAULT_OUTPUT_PATH = 'docs/gcd_xivanalysis_top_rankings_recompute_completion_manifest_latest.json'

function parseArgs(argv) {
  const args = new Map()

  for (let index = 0; index < argv.length; index += 1) {
    const current = argv[index]

    if (!current.startsWith('--')) {
      throw new Error(`不支援的位置參數：${current}`)
    }

    const key = current.slice(2)
    const value = argv[index + 1]

    if (!value || value.startsWith('--')) {
      throw new Error(`參數 --${key} 需要指定值`)
    }

    args.set(key, value)
    index += 1
  }

  return args
}

function resolveRepoPath(inputPath) {
  return path.isAbsolute(inputPath) ? inputPath : path.join(ROOT_DIR, inputPath)
}

function toRepoPath(inputPath) {
  return path.relative(ROOT_DIR, inputPath).split(path.sep).join('/')
}

function normalizeRepoPath(inputPath) {
  if (!inputPath) {
    return ''
  }

  const slashPath = String(inputPath).replaceAll('\\', '/')
  const absoluteLike = /^[A-Za-z]:\//.test(slashPath) || slashPath.startsWith('/')

  if (!absoluteLike) {
    return slashPath.replace(/^\.\//, '')
  }

  return path.relative(ROOT_DIR, path.normalize(slashPath)).split(path.sep).join('/')
}

async function readJson(filePath) {
  return JSON.parse(await readFile(filePath, 'utf8'))
}

function numberValue(value, fallback = 0) {
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric : fallback
}

function summaryFromRecompute(filePath, report) {
  const summary = report.summary ?? {}

  return {
    file: toRepoPath(filePath),
    checked: numberValue(summary.checked),
    matched: numberValue(summary.matched),
    mismatched: numberValue(summary.mismatched),
    errors: numberValue(summary.errors),
    gt_0_5: numberValue(summary.gt_0_5),
    gt_1_0: numberValue(summary.gt_1_0),
  }
}

function versionFromFile(filePath) {
  const match = path.basename(filePath).match(/_v(\d+)(?:_|\.json$)/)
  return match ? Number(match[1]) : 0
}

function candidateIsComplete(candidate, requiredMatched) {
  return candidate.matched >= requiredMatched && candidate.mismatched === 0 && candidate.errors === 0
}

function sortCandidates(candidates, requiredMatched) {
  return [...candidates].sort((left, right) => {
    const leftComplete = candidateIsComplete(left, requiredMatched) ? 1 : 0
    const rightComplete = candidateIsComplete(right, requiredMatched) ? 1 : 0

    if (leftComplete !== rightComplete) {
      return rightComplete - leftComplete
    }

    if (left.matched !== right.matched) {
      return right.matched - left.matched
    }

    if (left.mismatched !== right.mismatched) {
      return left.mismatched - right.mismatched
    }

    if (left.errors !== right.errors) {
      return left.errors - right.errors
    }

    if (left.gt_1_0 !== right.gt_1_0) {
      return left.gt_1_0 - right.gt_1_0
    }

    if (left.gt_0_5 !== right.gt_0_5) {
      return left.gt_0_5 - right.gt_0_5
    }

    return versionFromFile(right.file) - versionFromFile(left.file) || left.file.localeCompare(right.file)
  })
}

async function loadSameSourceRecomputeCandidates(docsDir) {
  const candidatesBySourceAudit = new Map()
  const entries = await readdir(docsDir, { withFileTypes: true })

  for (const entry of entries) {
    if (!entry.isFile()) {
      continue
    }

    if (!entry.name.startsWith('gcd_xivanalysis_recompute_top_rankings_') || !entry.name.endsWith('.json')) {
      continue
    }

    const filePath = path.join(docsDir, entry.name)

    try {
      const report = await readJson(filePath)
      const sourceReport = normalizeRepoPath(report.source_report)

      if (!sourceReport || !report.summary) {
        continue
      }

      const candidate = summaryFromRecompute(filePath, report)
      const candidates = candidatesBySourceAudit.get(sourceReport) ?? []
      candidates.push(candidate)
      candidatesBySourceAudit.set(sourceReport, candidates)
    } catch (error) {
      console.warn(`略過無法解析的 recompute JSON：${toRepoPath(filePath)} (${error.message})`)
    }
  }

  return candidatesBySourceAudit
}

function buildEntry(sourceEntry, candidates) {
  const requiredMatched = numberValue(sourceEntry.matched)
  const sortedCandidates = sortCandidates(candidates, requiredMatched)
  const selectedCandidate = sortedCandidates[0] ?? null
  const complete = selectedCandidate ? candidateIsComplete(selectedCandidate, requiredMatched) : false
  const status = complete
    ? 'complete'
    : selectedCandidate
      ? 'incomplete_recompute_evidence'
      : 'missing_recompute_evidence'
  const output = {
    encounter_key: sourceEntry.encounter_key,
    job: sourceEntry.job,
    source_audit_file: normalizeRepoPath(sourceEntry.audit_file),
    required_matched: requiredMatched,
    source_audit_errors: numberValue(sourceEntry.errors),
    status,
  }

  if (complete) {
    output.selected_recompute_file = selectedCandidate.file
    output.selected_recompute_summary = {
      checked: selectedCandidate.checked,
      matched: selectedCandidate.matched,
      mismatched: selectedCandidate.mismatched,
      errors: selectedCandidate.errors,
      gt_0_5: selectedCandidate.gt_0_5,
      gt_1_0: selectedCandidate.gt_1_0,
    }
    output.candidate_recompute_files = sortedCandidates
    return output
  }

  output.candidate_count = sortedCandidates.length
  output.best_candidate = selectedCandidate
  return output
}

function buildSummary(sourceManifestPath, entries) {
  const completeEntries = entries.filter((entry) => entry.status === 'complete')
  const entriesWithCandidate = entries.filter((entry) => (
    entry.status === 'complete'
    || numberValue(entry.candidate_count) > 0
    || Boolean(entry.selected_recompute_file)
  ))
  const selectedSummaries = entries
    .map((entry) => entry.selected_recompute_summary ?? entry.best_candidate)
    .filter(Boolean)

  return {
    schema_version: 1,
    generated_at_iso: new Date().toISOString(),
    scope: 'top-rankings 每副本每職業排行榜前 100 名；以 v1908 stored 外站答案稽核檔作為 source_report，檢查本地演算法 recompute 是否 matched>=stored matched 且 mismatched/errors=0。',
    source_manifest: toRepoPath(sourceManifestPath),
    expected_combo_count: entries.length,
    complete_combo_count: completeEntries.length,
    incomplete_combo_count: entries.filter((entry) => entry.status === 'incomplete_recompute_evidence').length,
    missing_combo_count: entries.length - completeEntries.length,
    with_any_same_source_recompute_count: entriesWithCandidate.length,
    total_matched_in_selected_recompute: selectedSummaries.reduce((sum, summary) => sum + numberValue(summary.matched), 0),
    total_mismatched_in_selected_recompute: selectedSummaries.reduce((sum, summary) => sum + numberValue(summary.mismatched), 0),
    total_errors_in_selected_recompute: selectedSummaries.reduce((sum, summary) => sum + numberValue(summary.errors), 0),
  }
}

async function main() {
  const args = parseArgs(process.argv.slice(2))
  const sourceManifestPath = resolveRepoPath(args.get('source-manifest') ?? DEFAULT_SOURCE_MANIFEST)
  const outputPath = resolveRepoPath(args.get('output-path') ?? DEFAULT_OUTPUT_PATH)
  const docsDir = resolveRepoPath(args.get('docs-dir') ?? 'docs')
  const sourceManifest = await readJson(sourceManifestPath)
  const recomputeCandidatesByAudit = await loadSameSourceRecomputeCandidates(docsDir)
  const entries = sourceManifest.entries.map((sourceEntry) => {
    const auditFile = normalizeRepoPath(sourceEntry.audit_file)
    return buildEntry(sourceEntry, recomputeCandidatesByAudit.get(auditFile) ?? [])
  })
  const incompleteEntries = entries.filter((entry) => entry.status !== 'complete').map((entry) => ({
    encounter_key: entry.encounter_key,
    job: entry.job,
    source_audit_file: entry.source_audit_file,
    required_matched: entry.required_matched,
    candidate_count: entry.candidate_count ?? entry.candidate_recompute_files?.length ?? 0,
    best_candidate: entry.best_candidate ?? null,
  }))
  const manifest = {
    summary: buildSummary(sourceManifestPath, entries),
    entries,
    missing_combos: incompleteEntries,
  }

  await mkdir(path.dirname(outputPath), { recursive: true })
  await writeFile(outputPath, `${JSON.stringify(manifest, null, 2)}\n`, 'utf8')
  console.log(JSON.stringify(manifest.summary, null, 2))
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
