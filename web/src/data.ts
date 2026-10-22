// Measured results shown on the Home and How it works screens. Source files in evals/results/
// (cascade.json, codes_loinc.json, codes_icd10.json, ner_xlmr_int8.json); update them together.

export const HEADLINE = {
  cascadeF1: '0.955',
  fullyCorrect: '62%',
  toLlm: '33%',
  secondsPerDoc: '~1–2 s',
  costPerMonth: '$0.25',
}

export const EXTRACTION = [
  { system: 'Local model only (fine-tuned XLM-R, int8)', f1: '0.920', correct: '57.8%', llm: '0%', seconds: '0.15' },
  { system: 'Gemini only', f1: '0.955', correct: '59.4%', llm: '100%', seconds: '2.71' },
  { system: 'Cascade (validator routes to Gemini)', f1: '0.955', correct: '62.0%', llm: '32.8%', seconds: '1.19', best: true },
  { system: 'Perfect routing (ceiling)', f1: '0.956', correct: '63.4%', llm: '42.2%', seconds: '1.50' },
]

export const CODING = [
  { task: 'Lab test → LOINC', top1: '59.8%', top5: '81.0%', note: 'same test, any method: 73.6%' },
  { task: 'Diagnosis → ICD-10-CM (English)', top1: '43.6%', top5: '76.4%', note: 'with official coding rules' },
  { task: 'Diagnosis → ICD-10-CM (French)', top1: '44.2%', top5: '65.1%', note: 'no French code table used' },
]

export interface SampleInfo {
  title: string
  kind: 'Lab report' | 'Referral letter'
  lang: 'English' | 'French'
  scanned: boolean
}

// '/samples' returns file names like 'lab-report-fr-scanned.pdf'.
export function describeSample(name: string): SampleInfo {
  const lab = name.startsWith('lab')
  const fr = name.includes('-fr-')
  const scanned = name.includes('scanned')
  return {
    title: `${fr ? 'French' : 'English'} ${lab ? 'lab report' : 'referral letter'}`,
    kind: lab ? 'Lab report' : 'Referral letter',
    lang: fr ? 'French' : 'English',
    scanned,
  }
}
