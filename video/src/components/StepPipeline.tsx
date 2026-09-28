import React from 'react';
import {COLORS} from '../theme';
import {Reveal} from './Reveal';

/** 横向步骤流水线：编号卡片 + 箭头，逐个浮入。 */
export const StepPipeline: React.FC<{
  steps: {n: string; title: string; desc: string; hint?: string}[];
  startDelay?: number;
  stepDelay?: number;
}> = ({steps, startDelay = 24, stepDelay = 55}) => {
  return (
    <div style={{display: 'flex', alignItems: 'stretch', gap: 0}}>
      {steps.map((s, i) => (
        <React.Fragment key={s.n}>
          <Reveal
            delay={startDelay + i * stepDelay}
            y={30}
            style={{flex: 1, minWidth: 0}}
          >
            <div
              style={{
                height: '100%',
                background: COLORS.panel,
                border: `1px solid ${COLORS.border}`,
                borderTop: `5px solid ${COLORS.accent}`,
                borderRadius: 18,
                padding: '22px 22px 24px',
                boxSizing: 'border-box',
              }}
            >
              <div
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  width: 46,
                  height: 46,
                  borderRadius: 14,
                  background: 'rgba(91,140,255,0.18)',
                  border: '1.5px solid rgba(91,140,255,0.55)',
                  color: COLORS.accent,
                  fontSize: 22,
                  fontWeight: 800,
                }}
              >
                {s.n}
              </div>
              <div
                style={{
                  marginTop: 14,
                  fontSize: 27,
                  fontWeight: 750,
                  lineHeight: 1.35,
                }}
              >
                {s.title}
              </div>
              <div
                style={{
                  marginTop: 10,
                  fontSize: 20,
                  lineHeight: 1.55,
                  color: COLORS.dim,
                }}
              >
                {s.desc}
              </div>
              {s.hint ? (
                <div
                  style={{
                    marginTop: 12,
                    fontSize: 18,
                    lineHeight: 1.5,
                    color: COLORS.accent2,
                    fontFamily: "'Cascadia Code', Consolas, monospace",
                  }}
                >
                  {s.hint}
                </div>
              ) : null}
            </div>
          </Reveal>
          {i < steps.length - 1 ? (
            <Reveal
              delay={startDelay + i * stepDelay + 16}
              y={0}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: 52,
                flexShrink: 0,
              }}
            >
              <div
                style={{
                  color: COLORS.accent,
                  fontSize: 34,
                  fontWeight: 800,
                  opacity: 0.85,
                }}
              >
                →
              </div>
            </Reveal>
          ) : null}
        </React.Fragment>
      ))}
    </div>
  );
};
