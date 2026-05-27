const API_URL = 'https://api.anthropic.com/v1/messages';
const SUMMARY_MODEL = 'claude-sonnet-4-6';

function apiKey(): string {
  const key = import.meta.env.VITE_ANTHROPIC_API_KEY as string | undefined;
  if (!key) throw new Error('VITE_ANTHROPIC_API_KEY is not set. Add it to apps/web-demo/.env');
  return key;
}

async function callClaude(system: string, userMessage: string, model = SUMMARY_MODEL): Promise<string> {
  const res = await fetch(API_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'x-api-key': apiKey(),
      'anthropic-version': '2023-06-01',
      'anthropic-dangerous-direct-browser-access': 'true',
    },
    body: JSON.stringify({
      model,
      max_tokens: 1024,
      system,
      messages: [{ role: 'user', content: userMessage }],
    }),
  });

  if (!res.ok) {
    const err = await res.text();
    throw new Error(`Anthropic API error ${res.status}: ${err}`);
  }

  const data = await res.json();
  return data.content[0].text as string;
}

export async function generateSectionSummary(
  sectionTitle: string,
  formattedQA: string,
  tone: 'warm' | 'balanced' | 'directive',
): Promise<string> {
  const toneInstruction =
    tone === 'warm'
      ? 'Write in a warm, conversational tone — friendly, like a knowledgeable friend explaining things.'
      : tone === 'directive'
      ? 'Write in a clear, direct tone — crisp and unambiguous, like a well-written policy document.'
      : 'Write in a balanced, professional tone — clear and warm, suitable for any reader.';

  const system = `You are writing a section of a household guide for an au pair. The guide is written by the host family, addressed directly to the au pair.

The guide section is: "${sectionTitle}"

${toneInstruction}

Write a comprehensive summary of everything the family shared. The summary must:
- Be written in first person from the parents' perspective — use "we", "our", "us", and address the au pair directly as "you". For example: "We are a high-energy family and we love doing things together. You'll find that our evenings usually…"
- Use plain, simple English — short sentences, everyday words. The au pair's first language may not be English.
- Cover EVERY detail the family provided — nothing should be left out.
- Flow as natural paragraphs, not bullet points or headers.
- Be specific: use names, numbers, and exact details the family gave.
- Connect related details naturally (e.g. "Amara has a peanut allergy, so please always check labels before preparing her food").

Return only the summary text. No titles, no JSON, no preamble.`;

  const raw = await callClaude(system, formattedQA);
  return raw.trim();
}

export async function generateGuideFromSummaries(
  familyName: string,
  sectionSummaries: Record<string, { title: string; summary: string }>,
  tone: 'warm' | 'balanced' | 'directive' = 'balanced',
): Promise<string> {
  const toneInstruction =
    tone === 'warm'
      ? 'Write in a warm, conversational tone — friendly and personal throughout.'
      : tone === 'directive'
      ? 'Write in a clear, direct tone — crisp and unambiguous throughout.'
      : 'Write in a balanced, professional tone — clear and warm, suitable for any reader.';

  const sections = Object.values(sectionSummaries)
    .map(s => `## ${s.title}\n${s.summary}`)
    .join('\n\n');

  const system = `You are assembling a household guide for an au pair from a set of section summaries written by a host family.

${toneInstruction}

Your job:
- Weave the sections together into a single, cohesive document.
- Add natural linkage sentences between sections where relevant (e.g. referencing a child's allergy when it comes up in responsibilities AND in household info).
- Keep plain, simple English throughout.
- Do not add information that wasn't in the summaries.
- Return plain text paragraphs only — no markdown headers, no bullet points.`;

  const user = `Family name: ${familyName}

Section summaries:
${sections}

Write the connected guide.`;

  return (await callClaude(system, user)).trim();
}
