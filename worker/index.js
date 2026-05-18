/**
 * Precedent API Proxy — Cloudflare Worker
 * Routes: POST /analyze  →  Claude API
 *         POST /brief     →  Claude API (weekly brief generation)
 *
 * Deploy:
 *   wrangler secret put ANTHROPIC_API_KEY
 *   wrangler deploy
 */

const ALLOWED_ORIGINS = [
  'https://thanen-dev.github.io',
  'http://localhost:8765',
  'http://127.0.0.1:8765',
];

const CLAUDE_MODEL   = 'claude-sonnet-4-6';
const CLAUDE_API_URL = 'https://api.anthropic.com/v1/messages';

// ── Precedent intelligence context (baked in at deploy time) ─────────────────
// This is the distilled knowledge base. Update by redeploying the worker
// after running: python3 site/build.py --export-context
const PRECEDENT_CONTEXT = `
=== LEADER PROFILES ===

Aun Pornmoniroth (aun_pornmoniroth) — Deputy Prime Minister; Minister of Economy and Finance
  [GROWTH_THEORY] Macroeconomic stability as the precondition. Fiscal-first: budget discipline, low inflation, revenue mobilisation, stable riel. Not an industrialiser — a stabiliser. Relies on FDI and private sector to drive growth within that stable envelope.
  [TIME_HORIZON] Medium-term fiscal cycles (3–5 years). Not a long-horizon structural thinker.
  [INSTITUTION_VS_RELATIONSHIP] Firmly institutional. MEF processes, SNEC frameworks, IMF consultation cycles. Not a relationship-first operator.
  [DEPENDENCY_ASSUMPTIONS] Accepts FDI dependence as necessary. Hedges via diversification of source countries but does not challenge the FDI-led model itself.
  [GLOBAL_POSITIONING] Bilateral pragmatism with multilateral cover. Pursues US-Cambodia trade while maintaining China FDI flows. Rapid bilateral concessions to the US at the expense of multilateral EBA restoration strategy.
  [RISK_TOLERANCE] Low. Incremental improvement. Never makes bold unilateral bets.
  [CONSISTENCY] High — 12 years at MEF with consistent fiscal-first doctrine.

Cham Nimul (cham_nimul) — Minister of Commerce
  [GROWTH_THEORY] Export-led growth via trade agreement stack. WTO, RCEP, ASFTA, bilateral FTAs as the architecture for sustained export growth.
  [TIME_HORIZON] Long — trade architecture takes 5–10 years to produce results.
  [INSTITUTION_VS_RELATIONSHIP] Strongly institutional. Rules-based trade framework, WTO dispute mechanisms.
  [DEPENDENCY_ASSUMPTIONS] Accepts export concentration risk but believes diversification comes through more agreements, not industrial policy.
  [GLOBAL_POSITIONING] Multilateral rules-based positioning. EU EBA restoration via governance reform compliance. Directly undermined by Pornmoniroth's rapid bilateral US concessions.
  [RISK_TOLERANCE] Medium — willing to engage on governance reforms if required for trade access.
  [CONSISTENCY] High on trade architecture; tension with bilateral pragmatists in cabinet.

Chea Serey (chea_serey) — Governor, National Bank of Cambodia
  [GROWTH_THEORY] Financial deepening and de-dollarisation as structural prerequisites for monetary sovereignty. Bakong digital currency as instrument.
  [TIME_HORIZON] Long — 10+ year de-dollarisation program.
  [INSTITUTION_VS_RELATIONSHIP] Strongly institutional. NBC frameworks, BIS standards, FATF compliance.
  [DEPENDENCY_ASSUMPTIONS] USD dependency identified as structural vulnerability. Every large USD-denominated FDI deal deepens the problem she is trying to solve.
  [GLOBAL_POSITIONING] Monetary sovereignty through Bakong. CONFLICT: Hun Manet's FDI-first growth model deepens dollarisation that Serey's program is trying to dismantle.
  [RISK_TOLERANCE] Medium-high on monetary experimentation. Conservative on financial stability.
  [CONSISTENCY] Consistent on de-dollarisation since 2020.

Chea Vandeth (chea_vandeth) — Minister of Post and Telecommunications; Digital Economy Architect
  [GROWTH_THEORY] Digital infrastructure as growth multiplier. Government digitisation unlocks FDI quality and tax compliance simultaneously.
  [TIME_HORIZON] Medium — 5-year Digital Economy and Society Policy Framework 2021-2035.
  [INSTITUTION_VS_RELATIONSHIP] Institutional. Policy frameworks, ASEAN Digital Awards, international standards.
  [DEPENDENCY_ASSUMPTIONS] Technology dependency on Chinese suppliers mitigated by policy localisation requirements.
  [GLOBAL_POSITIONING] Digital sovereignty with practical Chinese technology partnerships.
  [RISK_TOLERANCE] Medium-high — willing to accelerate reforms faster than traditional ministries.
  [CONSISTENCY] High since 2020.

Hang Chuon Naron (hang_chuon_naron) — Deputy Prime Minister; Minister of Education
  [GROWTH_THEORY] Human capital as long-run growth driver. Education reform as the prerequisite for moving up the value chain beyond garments.
  [TIME_HORIZON] Very long — 15–20 year human capital investment horizon.
  [INSTITUTION_VS_RELATIONSHIP] Strongly institutional. Academic credentials (PhD x2), international education standards.
  [DEPENDENCY_ASSUMPTIONS] Current FDI concentration in low-skill manufacturing is a trap. Education is the exit.
  [GLOBAL_POSITIONING] Multilateral engagement — UNESCO, ADB education frameworks.
  [RISK_TOLERANCE] Low on disruption; high on sustained reform.
  [CONSISTENCY] Consistent since 2013.

Hem Vanndy (hem_vanndy) — Minister of Industry, Science, Technology and Innovation
  [GROWTH_THEORY] Industry 4.0 and SME formalisation. Economic diversification away from garment concentration. Khmer Enterprise as vehicle.
  [TIME_HORIZON] Medium — 5-year industrial policy cycles.
  [INSTITUTION_VS_RELATIONSHIP] Mixed — uses Khmer Enterprise (relationship-based fund) within policy framework.
  [DEPENDENCY_ASSUMPTIONS] Garment concentration is existential risk. Diversification is urgent.
  [GLOBAL_POSITIONING] Pitches Cambodia to Singapore investors. Entrepreneurship-enabling frame rather than state-led industrial policy.
  [RISK_TOLERANCE] Medium — willing to experiment with SME programs.

Hun Manet (hun_manet) — Prime Minister of Cambodia
  [GROWTH_THEORY] FDI-and-infrastructure-led growth. Win budget priority when resources constrained. Rule-of-law narrative for international investors. Pentagonal Strategy as the framework.
  [TIME_HORIZON] Medium — 5-year political cycle with 2028 election horizon.
  [INSTITUTION_VS_RELATIONSHIP] Claims institutional but operates through relationship networks. Rule-of-law narrative is structurally falsified by the judiciary Hun Sen built.
  [DEPENDENCY_ASSUMPTIONS] Accepts Chinese FDI concentration as necessary given limited alternatives. Funan Canal as signature infrastructure.
  [GLOBAL_POSITIONING] Hedging between China and US. Simultaneous pursuit of US trade normalisation and Chinese infrastructure deals.
  [RISK_TOLERANCE] Medium — willing to make bold gestures (Funan Canal) but avoids institutional confrontation.
  [CONSISTENCY] Low — doctrine evolving; rule-of-law rhetoric inconsistent with systemic practice.

Hun Sen (hun_sen) — President of the Senate; Former Prime Minister (1985–2023)
  [GROWTH_THEORY] Political stability as the foundation of all economic activity. Stability enables FDI, stability enables growth. Not an economist's growth model — a power model.
  [TIME_HORIZON] Generational — built institutions over 38 years to outlast him.
  [INSTITUTION_VS_RELATIONSHIP] Strongly relationship-based. Built judiciary, military, and police through personal loyalty networks, not meritocratic institutions.
  [DEPENDENCY_ASSUMPTIONS] China dependency is a feature, not a bug — provides regime insurance against Western human rights pressure.
  [GLOBAL_POSITIONING] China as strategic partner, ASEAN as legitimacy cover, West as manageable pressure. CONFLICT: Aun Pornmoniroth's bilateral US concessions directly undermine Hun Sen's China-first insurance logic.
  [RISK_TOLERANCE] Very high on political risk. Low on economic experimentation.
  [CONSISTENCY] Extremely high — 38-year consistent doctrine.

Say Sam Al (say_sam_al) — Minister of Environment
  [GROWTH_THEORY] Green investment as new FDI category. Environmental compliance unlocks ASEAN green finance.
  [TIME_HORIZON] Medium — ASEAN green frameworks, 2030 targets.
  [INSTITUTION_VS_RELATIONSHIP] Institutional on paper; in practice, land concession system operates through relationship networks that contradict environmental mandate.
  [DEPENDENCY_ASSUMPTIONS] FDI in land and agriculture creates intrinsic conflict with forest protection.
  [RISK_TOLERANCE] Low — politically constrained by land concession interests.

Sok Siphana (sok_siphana) — Senior Minister; Trade and Economic Affairs
  [GROWTH_THEORY] Rules-based trade integration. WTO accession as model — Cambodia's 1999–2004 WTO process as his signature achievement. Multilateral framework as growth enabler.
  [TIME_HORIZON] Long — trade architecture.
  [INSTITUTION_VS_RELATIONSHIP] Strongly institutional. JD, LLM. WTO frameworks, international arbitration.
  [DEPENDENCY_ASSUMPTIONS] Trade preference dependence (EBA, GSP) is a vulnerability requiring active hedging through diversification.
  [GLOBAL_POSITIONING] Rules-based multilateral order. Sceptical of bilateral shortcuts.
  [RISK_TOLERANCE] Medium.
  [CONSISTENCY] High since 1999.

Sun Chanthol (sun_chanthol) — Deputy Prime Minister; Co-Chair, China-Cambodia Intergovernmental Coordination
  [GROWTH_THEORY] Large infrastructure and FDI as growth driver. China relationship as primary capital source. CAFTA-analogue tariff negotiator background.
  [TIME_HORIZON] Long infrastructure cycles.
  [INSTITUTION_VS_RELATIONSHIP] Relationship-first. China Co-Chair role is the apex relationship management post.
  [DEPENDENCY_ASSUMPTIONS] Chinese FDI is both necessary and manageable. Funan Canal is his domain.
  [GLOBAL_POSITIONING] China-first. CONFLICT: Chea Serey's NBC de-dollarisation is undermined by every Chinese USD-denominated deal Chanthol facilitates.
  [RISK_TOLERANCE] High — willing to accept large debt exposures for infrastructure.

=== ACTIVE CONFLICTS (14 detected) ===

1. [HIGH RISK] GLOBAL_POSITIONING_LOGIC: Aun Pornmoniroth vs Cham Nimul
   A: Bilateral pragmatism — rapid concessions to the US on trade to secure market access
   B: Rules-based multilateral positioning — EBA restoration requires governance reform compliance, not bilateral shortcuts
   CONFLICT: Pornmoniroth's US bilateral concessions bypass the multilateral EBA restoration architecture Nimul is building. Both cannot be implemented simultaneously.
   BREAKING POINT: EU EBA re-engagement negotiations, 2026–2027

2. [HIGH RISK] GROWTH_THEORY: Hun Manet vs Chea Serey
   A: FDI-and-infrastructure growth — every large deal is a win regardless of currency denomination
   B: De-dollarisation as monetary sovereignty — USD-denominated FDI deepens the dependency Serey is trying to dismantle
   CONFLICT: Every dollar of FDI Manet courts deepens dollarisation that Serey's Bakong program is trying to dismantle.
   BREAKING POINT: First large FDI deal requiring NBC carve-out or USD debt service guarantee, 2026

3. [HIGH RISK] INSTITUTION_VS_RELATIONSHIP: Hun Manet vs Hun Sen
   A: Rule-of-law FDI narrative — Cambodia is reforming institutions to attract quality FDI
   B: Relationship-based judiciary and security apparatus — loyalty networks, not rule of law
   CONFLICT: Manet's rule-of-law FDI narrative is structurally falsified by the judiciary Hun Sen built. The first high-profile FDI dispute reaching Cambodian courts will expose this.
   BREAKING POINT: First CPP-connected FDI dispute reaching courts or international arbitration, 2026–2027

4. [HIGH RISK] DEPENDENCY_ASSUMPTIONS: Sun Chanthol vs Chea Serey
   A: Chinese FDI and infrastructure as necessary and manageable — Funan Canal
   B: USD-denominated debt exposure as monetary sovereignty risk
   CONFLICT: Chanthol's China-infrastructure deals create USD debt service obligations that directly undermine Serey's de-dollarisation program.

5. [MEDIUM RISK] GLOBAL_POSITIONING: Hun Sen vs Aun Pornmoniroth
   A: China as strategic insurance against Western pressure — dependency is a feature
   B: US trade normalisation as economic priority
   CONFLICT: Pornmoniroth's bilateral US concessions undermine Hun Sen's China-first insurance logic.

6. [MEDIUM RISK] GROWTH_THEORY: Hun Manet vs Sok Siphana
   A: Infrastructure-led FDI growth, bilateral deal-making
   B: Rules-based multilateral trade framework
   CONFLICT: Manet's bilateral infrastructure deals bypass the multilateral framework Siphana built.

=== HISTORICAL CASES ===
LKA_FISCAL_COLLAPSE_2010_2022 | Sri Lanka 2010–2022: Chinese infrastructure debt trap — Hambantota port → sovereign default 2022. Lesson: Infrastructure debt + export sector shock = fiscal collapse.
BGD_GARMENT_2012 | Bangladesh 2005–2020: Export concentration trap — 80% garments, no diversification, perpetual vulnerability. Lesson: Concentration without diversification creates structural fragility.
BGD_RANA_PLAZA_2013 | Bangladesh 2013–2018: Forced labour reforms post-Rana Plaza — improved standards but cost short-term competitiveness. Lesson: Reforms under crisis pressure are more costly than proactive reform.
VNM_WTO_2007 | Vietnam 2007–2012: WTO accession-driven institutional reform unlocked FDI quality upgrade. Lesson: Credible institutional reform multiplies FDI value.
MUS_EPZ_1970_1995 | Mauritius 1970–1995: Garment EPZ → diversification to financial services and tourism over 25 years. Lesson: Deliberate sectoral diversification is achievable but requires 20+ year commitment.
HND_CAFTA_POST_2005 | Honduras 2005–2018: CAFTA transition — labour standard upgrades retained preferential access. Lesson: Proactive standard compliance costs less than reactive reform.
ARG_FISCAL_COLLAPSE_2001 | Argentina 1999–2005: Currency peg collapse — convertibility → default → heterodox recovery. Lesson: Rigid currency arrangements collapse under current account stress.
IDN_AFC_RECOVERY_1998 | Indonesia 1997–2003: IMF bailout with structural reforms after FDI flight. Lesson: External shock requires institutional flexibility; relationship-based systems adapt slowly.
MEX_NAFTA_LABOR_1994 | Mexico 1994–2004: NAFTA side agreements began labour reform under trade framework pressure. Lesson: Trade framework leverage is more effective than bilateral pressure for institutional reform.
`;

// ── System prompts ────────────────────────────────────────────────────────────
const ANALYZER_SYSTEM = `You are the Precedent political intelligence engine for Cambodia.

You have deep knowledge of Cambodia's 11 senior officials, their doctrine across 7 analytical dimensions (growth theory, time horizon, institution vs relationship, dependency assumptions, global positioning, risk tolerance, consistency), 14 detected conflicts between them, and 9 historical structural analogues.

${PRECEDENT_CONTEXT}

INSTRUCTIONS:
When given a news signal or policy announcement about Cambodia, produce a structured analysis with exactly these sections:

SIGNAL TYPE: [1-3 word category, e.g. "Infrastructure / FDI" or "Trade / EBA" or "Monetary Policy"]

LEADERS IMPLICATED: [List relevant leaders with the specific dimension affected]

DOCTRINE MATCH: [For each implicated leader — is this ON-MODEL (expected given their doctrine) or OFF-MODEL (surprising)? Cite their specific doctrine position and confidence 0-100%]

CONFLICTS ACTIVATED: [Which of the 14 active conflicts does this signal touch? Explain the mechanism]

HISTORICAL TWIN: [Closest historical case from the database, similarity %, key structural lesson for Cambodia]

RISK FLAG: [HIGH / MEDIUM / LOW — one sentence justification citing specific numbers or mechanisms]

WHAT TO WATCH: [One specific, measurable leading indicator. E.g. "NBC quarterly report on USD-denominated bank liabilities — if rising quarter-on-quarter, the fiscal collision is accelerating"]

Rules:
- Be direct and specific. No hedging language like "might" or "could potentially".
- Cite exact doctrine positions and conflict explanations from the profiles.
- If the signal is not Cambodia-related, respond only: "SIGNAL NOT CAMBODIA-RELATED"
- Format output as plain text with clear section headers using the exact labels above.
- Keep total output under 600 words.`;

const BRIEF_SYSTEM = `You are the Precedent weekly brief generator for Cambodia political intelligence.

${PRECEDENT_CONTEXT}

Generate a concise, structured weekly brief. Format:

PRECEDENT WEEKLY BRIEF — [CURRENT PERIOD]

── THIS WEEK'S SIGNAL ──
[Synthesize the most significant recent development provided]
Doctrine lens: [What it reveals through Precedent's 7-dimension framework]

── CONFLICT STATUS ──
[Which of the 14 active conflicts is most activated right now? Why?]

── HISTORICAL ECHO ──
[Most relevant historical case from the database. What's the structural parallel?]

── LEADER TO WATCH ──
[One leader whose recent behavior is most diagnostically significant]

── RISK INDICATOR ──
Current level: [HIGH/MEDIUM/LOW]
[What changed and why]

Rules: Direct, no hedging, cite specific doctrine positions. 500 words maximum.`;

// ── CORS helpers ──────────────────────────────────────────────────────────────
function corsHeaders(origin) {
  const allowed = ALLOWED_ORIGINS.includes(origin) ? origin : ALLOWED_ORIGINS[0];
  return {
    'Access-Control-Allow-Origin': allowed,
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Max-Age': '86400',
  };
}

// ── Main handler ──────────────────────────────────────────────────────────────
export default {
  async fetch(request, env) {
    const origin  = request.headers.get('Origin') || '';
    const cors    = corsHeaders(origin);
    const url     = new URL(request.url);

    if (request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: cors });
    }

    if (request.method !== 'POST') {
      return new Response('Method not allowed', { status: 405, headers: cors });
    }

    // Rate limiting: simple check via CF
    const ip = request.headers.get('CF-Connecting-IP') || 'unknown';

    let body;
    try { body = await request.json(); } catch {
      return new Response(JSON.stringify({ error: 'Invalid JSON' }), { status: 400, headers: { ...cors, 'Content-Type': 'application/json' } });
    }

    const route = url.pathname;

    if (route === '/analyze') {
      const signal = (body.signal || '').trim().slice(0, 2000);
      if (!signal) {
        return new Response(JSON.stringify({ error: 'signal required' }), { status: 400, headers: { ...cors, 'Content-Type': 'application/json' } });
      }

      const claude = await fetch(CLAUDE_API_URL, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-api-key': env.ANTHROPIC_API_KEY,
          'anthropic-version': '2023-06-01',
        },
        body: JSON.stringify({
          model: CLAUDE_MODEL,
          max_tokens: 1200,
          system: ANALYZER_SYSTEM,
          messages: [{ role: 'user', content: signal }],
        }),
      });

      const data = await claude.json();
      const text = data?.content?.[0]?.text || '';
      return new Response(JSON.stringify({ analysis: text }), {
        headers: { ...cors, 'Content-Type': 'application/json' },
      });
    }

    if (route === '/brief') {
      const context = (body.context || 'No additional context provided.').slice(0, 1000);
      const claude = await fetch(CLAUDE_API_URL, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-api-key': env.ANTHROPIC_API_KEY,
          'anthropic-version': '2023-06-01',
        },
        body: JSON.stringify({
          model: CLAUDE_MODEL,
          max_tokens: 1500,
          system: BRIEF_SYSTEM,
          messages: [{ role: 'user', content: `Generate the weekly brief. Additional context: ${context}` }],
        }),
      });
      const data = await claude.json();
      const text = data?.content?.[0]?.text || '';
      return new Response(JSON.stringify({ brief: text }), {
        headers: { ...cors, 'Content-Type': 'application/json' },
      });
    }

    return new Response('Not found', { status: 404, headers: cors });
  },
};
