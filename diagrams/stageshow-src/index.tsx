import { Stage, Connector, States, Check, type Act, type Rect } from '../../kit'
import './defect-loop.css'

// The roadmap defect loop as a system story, no cursor. One round runs left to
// right: findings gather into the Decider, confirmed bugs go through the Bug
// fixer's gates into PRs, Brad acts on each PR, and the outcomes travel back
// over the top to the Decider and the Coordinator, which starts the next
// round. The Coach runs whenever anything in the field runs, changes nothing,
// and sends numbered feedback items that each role answers on its next run.

type S = { phase: number; clearing: boolean }
const START: S = { phase: 0, clearing: false }
const POSTER: S = { phase: 6, clearing: false }

const FINDERS = ['Trail of Bits', 'Shit Mountain', 'tech-debt-audit', 'Open Code Review']
const GATES = ['Strict tsc · CRAP', 'Mutation', 'Incremental review', 'Fresh reviewer']
const PRS = [
  { id: '#41', done: 'Merged', tone: 'merged' },
  { id: '#42', done: 'Fix requested', tone: 'repair' },
  { id: '#43', done: 'Closed', tone: 'closed' },
] as const

const script = async (a: Act<S>) => {
  a.mark('start'); await a.wait(900)
  a.mark('findings'); await a.set({ phase: 1 }); await a.wait(1500)
  a.mark('confirm'); await a.set({ phase: 2 }); await a.wait(1700)
  a.mark('gates'); await a.set({ phase: 3 }); await a.wait(1900)
  a.mark('prs'); await a.set({ phase: 4 }); await a.wait(1500)
  a.mark('brad'); await a.set({ phase: 5 }); await a.wait(2000)
  a.mark('outcomes'); await a.set({ phase: 6 }); await a.wait(3200)
  // The Coordinator's next round is the visible cause of the reset.
  a.mark('next'); await a.set({ clearing: true }); await a.wait(500)
  await a.set({ phase: 0, clearing: false }); await a.wait(600); a.mark('done')
}

const mid = (r: Rect) => ({ x: r.x + r.width / 2, y: r.y + r.height / 2 })
const right = (r: Rect) => ({ x: r.x + r.width, y: r.y + r.height / 2 })
const left = (r: Rect) => ({ x: r.x, y: r.y + r.height / 2 })

export default function DefectLoop() {
  return (
    <Stage<S> width={1120} height={623} initial={START} poster={POSTER} script={script} greys="cool" accent="#2f6fd6" className="dl">
      {(s, rect) => {
        const live = !s.clearing
        const finders = FINDERS.map((_, i) => rect(`finder-${i}`))
        const decider = rect('decider'), fixer = rect('fixer'), prs = rect('prs'), human = rect('human'), coord = rect('coord')
                const measured = [decider, fixer, prs, human, coord, ...finders].every(r => r.width > 0)
        const p = s.phase
        // The top rail: PRs up, across to the Decider (outcomes), on to the Coordinator (next round).
        const railY = 92
        const repairY = 448
        const prTop = { x: prs.x + prs.width / 2, y: prs.y }
        const deciderTop = { x: decider.x + decider.width / 2, y: decider.y }
        const coordRight = right(coord)
        return <>
          {/* The Coach sees everything inside this line. */}
          <div className="dl-coach-field" data-on={p >= 1 || undefined} />
          <div className="dl-coach" data-on={p >= 1 || undefined}>
            <i className="dl-coach-dot" data-sent={p >= 6 || undefined} />
            <strong>Coach</strong>
            <States align="start" value={p >= 6 ? 'sent' : 'watch'} states={{ watch: 'watching every run', sent: 'feedback to each role' }} />
          </div>

          <section className="dl-node dl-coord" data-target="coord">
            <strong>Coordinator</strong>
            <States align="start" value={p >= 6 ? 'next' : 'run'} states={{ run: 'Round planned · top areas first', next: 'All PRs addressed · next round' }} />
          </section>

          {FINDERS.map((name, i) => (
            <section key={name} className="dl-pill dl-finder" data-target={`finder-${i}`} style={{ top: 150 + i * 56 }} data-on={p >= 1 || undefined}>{name}{i === 3 && <small>next part · until usage runs out</small>}</section>
          ))}

          <section className="dl-node dl-card dl-decider" data-target="decider" data-on={p >= 1 || undefined}>
            <header><strong>Decider</strong><States align="end" value={p >= 1 ? 'in' : 'none'} states={{ none: 'waiting', in: '7 findings' }} /></header>
            <div className="dl-line" data-on={p >= 2 || undefined}><Check on={p >= 2} size={14} /><span>5 confirmed</span><em>repro or 2 checks</em></div>
            <div className="dl-line dl-line--muted" data-on={p >= 2 || undefined}><span className="dl-q">?</span><span>2 suspected</span></div>
          </section>

          <section className="dl-pill dl-human" data-target="human" data-on={p >= 2 || undefined}>Human review<b>2</b></section>

          <section className="dl-node dl-card dl-fixer" data-target="fixer" data-on={p >= 3 || undefined}>
            <header><strong>Bug fixer</strong><span>one fix per PR</span></header>
            {GATES.map((g, i) => (
              <div key={g} className="dl-gate" style={{ ['--i' as string]: i }}><Check on={p >= 3} pending={false} size={13} /><span>{g}</span></div>
            ))}
            <footer>Approval binds code + PR text<br />Never merges or edits its tests</footer>
          </section>

          <section className="dl-node dl-card dl-prs" data-target="prs" data-on={p >= 4 || undefined}>
            <header><strong>PRs</strong><span>no limit</span></header>
            {PRS.map((pr, i) => (
              <div key={pr.id} className="dl-pr" data-target={`pr-${i}`} data-on={p >= 4 || undefined} data-tone={p >= 5 ? pr.tone : 'open'} style={{ ['--i' as string]: i }}>
                <span className="dl-pr-id">{pr.id}</span>
                <States align="end" value={p >= 5 ? 'done' : 'open'} states={{ open: 'Waiting on Brad', done: pr.done }} />
              </div>
            ))}
          </section>

          {measured && <>
            {finders.map((f, i) => <Connector key={i} className="dl-in" from={right(f)} to={left(decider)} route="step" show={live && p >= 1} dots="none" arrow={i === 1} />)}
            <Connector className="dl-flow" from={right(decider)} to={left(fixer)} route="straight" show={live && p >= 3} dots="none" arrow label="confirmed" />
            <Connector className="dl-side" from={{ x: decider.x + decider.width / 2, y: decider.y + decider.height }} to={{ x: decider.x + decider.width / 2, y: human.y }} route="straight" show={live && p >= 2} dots="none" arrow dashed />
            <Connector className="dl-flow" from={right(fixer)} to={left(prs)} route="straight" show={live && p >= 4} dots="none" arrow label="gates pass" />
            <Connector className="dl-side" from={right(human)} to={{ x: fixer.x + 44, y: fixer.y + fixer.height }} route="h" show={live && p >= 2} dots="none" arrow dashed label="Austin decides" labelAt={.4} />
            <svg className="dl-rail dl-repair-path" data-on={(live && p >= 5) || undefined} aria-hidden>
              <path pathLength={1} d={`M${prs.x + 40} ${prs.y + prs.height}V${repairY - 8}Q${prs.x + 40} ${repairY} ${prs.x + 32} ${repairY}H${fixer.x + fixer.width - 52}Q${fixer.x + fixer.width - 44} ${repairY} ${fixer.x + fixer.width - 44} ${repairY - 8}V${fixer.y + fixer.height + 4}`} />
              <path className="dl-rail-tip" d={`M${fixer.x + fixer.width - 49} ${fixer.y + fixer.height + 11}L${fixer.x + fixer.width - 44} ${fixer.y + fixer.height + 4}L${fixer.x + fixer.width - 39} ${fixer.y + fixer.height + 11}`} />
            </svg>
            <span className="dl-rail-label dl-repair-label" data-on={(live && p >= 5) || undefined} style={{ left: (prs.x + 40 + fixer.x + fixer.width - 44) / 2, top: repairY - 10 }}>Brad asks for a fix · repair 1 of 3 · new changes only</span>
            <svg className="dl-rail" data-on={(live && p >= 6) || undefined} aria-hidden>
              <path pathLength={1} d={`M${prTop.x} ${prTop.y}V${railY + 10}Q${prTop.x} ${railY} ${prTop.x - 10} ${railY}H${coordRight.x + 6}`} />
              <path className="dl-rail-branch" pathLength={1} d={`M${deciderTop.x} ${railY}V${deciderTop.y - 4}`} />
              <path className="dl-rail-tip" d={`M${coordRight.x + 12} ${railY - 5}L${coordRight.x + 5} ${railY}L${coordRight.x + 12} ${railY + 5}`} />
              <path className="dl-rail-tip dl-rail-tip--down" d={`M${deciderTop.x - 5} ${deciderTop.y - 11}L${deciderTop.x} ${deciderTop.y - 4}L${deciderTop.x + 5} ${deciderTop.y - 11}`} />
              <circle className="dl-rail-junction" cx={deciderTop.x} cy={railY} r={3.5} />
            </svg>
            <span className="dl-rail-label" data-on={(live && p >= 6) || undefined} style={{ left: (deciderTop.x + prTop.x) / 2, top: railY - 24 }}>outcomes + Brad's reasons</span>
          </>}

          {/* Outside the Coach's line: the yardsticks the outcomes feed. */}
          <div className="dl-node dl-card dl-yards" data-on={p >= 6 || undefined}>
          <section className="dl-yard dl-score">
            <header><strong>Scorecard</strong><span>Coach reads it</span></header>
            <p>Brad's comments · repair rounds · wait on Brad · Decider precision</p>
            <p className="dl-guard">Guardrail: merged and held 30 days, no revert</p>
          </section>
          <section className="dl-yard dl-test">
            <header><strong>Test set</strong><span>rerun on any change</span></header>
            <p>Closed or reverted PRs · missed bugs · held-out cases</p>
            <p className="dl-guard">Rerun in a sealed copy when prompts, model or tools change</p>
          </section>
          </div>
          <span className="dl-yard-label" data-on={p >= 6 || undefined}>PR outcomes feed both</span>
        </>
      }}
    </Stage>
  )
}
