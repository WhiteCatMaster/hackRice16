// Are the two contracts still the same file?
//
// `lib/contract.ts` and `lib/format.ts` are copies of the web app's, because
// both apps answer to the same backend and must describe it the same way. A
// copy is only safe if something notices when it stops being one — this is
// that something. It ignores the header comment above the first export, which
// is allowed to differ, and compares the rest byte for byte.
//
//   npm run contract:check
//
// It fails loudly rather than quietly, because the whole point of begin.md's
// shared contract is that drift between the layers shows up here instead of on
// stage.

import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const mobile = path.join(here, '..', 'lib')
const web = path.join(here, '..', '..', 'frontend', 'lib')

const FILES = ['contract.ts', 'format.ts']

/** Everything from the first non-comment, non-blank line onward. */
function body(source) {
  const lines = source.split('\n')
  const start = lines.findIndex((line) => {
    const t = line.trim()
    return t !== '' && !t.startsWith('//')
  })
  return lines
    .slice(start === -1 ? 0 : start)
    .join('\n')
    .trimEnd()
}

let failed = false

for (const file of FILES) {
  let ours
  let theirs
  try {
    ours = readFileSync(path.join(mobile, file), 'utf8')
    theirs = readFileSync(path.join(web, file), 'utf8')
  } catch (err) {
    console.error(`✗ ${file}: could not read both copies — ${err.message}`)
    failed = true
    continue
  }

  if (body(ours) === body(theirs)) {
    console.log(`✓ ${file} matches frontend/lib/${file}`)
    continue
  }

  failed = true
  console.error(`✗ ${file} has drifted from frontend/lib/${file}`)

  const a = body(ours).split('\n')
  const b = body(theirs).split('\n')
  for (let i = 0; i < Math.max(a.length, b.length); i++) {
    if (a[i] !== b[i]) {
      console.error(`    first difference at line ${i + 1} of the body:`)
      console.error(`      mobile:   ${a[i] ?? '(end of file)'}`)
      console.error(`      frontend: ${b[i] ?? '(end of file)'}`)
      break
    }
  }
  console.error(`    fix: cp frontend/lib/${file} mobile/lib/${file}`)
}

if (failed) {
  console.error(
    '\nThe two apps must describe the same backend the same way. Copy the web' +
      "\nversion across (the header comment above the first export may differ).",
  )
  process.exit(1)
}

console.log('\nBoth apps describe the same contract.')
