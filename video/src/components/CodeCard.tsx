import React from 'react';
import {COLORS, MONO} from '../theme';
import {Reveal} from './Reveal';

/** 代码卡片：窗口条 + 逐行浮入的代码。 */
export const CodeCard: React.FC<{
  title: string;
  lines: {text: string; tone?: 'plain' | 'key' | 'str' | 'dim'}[];
  startDelay?: number;
  lineStep?: number;
  caption?: string;
}> = ({title, lines, startDelay = 16, lineStep = 10, caption}) => {
  const toneColor: Record<string, string> = {
    plain: COLORS.text,
    key: COLORS.accent,
    str: COLORS.accent2,
    dim: COLORS.faint,
  };
  return (
    <div
      style={{
        background: 'rgba(10,16,32,0.78)',
        border: `1px solid ${COLORS.border}`,
        borderRadius: 18,
        overflow: 'hidden',
        boxShadow: '0 24px 60px rgba(0,0,0,0.35)',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          padding: '14px 22px',
          borderBottom: `1px solid ${COLORS.border}`,
          background: 'rgba(255,255,255,0.04)',
        }}
      >
        <div style={{display: 'flex', gap: 8}}>
          <span style={{width: 12, height: 12, borderRadius: 6, background: '#FF6B7A'}} />
          <span style={{width: 12, height: 12, borderRadius: 6, background: '#FFB454'}} />
          <span style={{width: 12, height: 12, borderRadius: 6, background: '#37D6A6'}} />
        </div>
        <div
          style={{
            marginLeft: 10,
            fontSize: 20,
            fontWeight: 650,
            color: COLORS.dim,
            fontFamily: MONO,
          }}
        >
          {title}
        </div>
      </div>
      <div style={{padding: '20px 24px 22px'}}>
        {lines.map((line, i) => (
          <Reveal key={`${line.text}-${i}`} delay={startDelay + i * lineStep} y={10}>
            <div
              style={{
                fontFamily: MONO,
                fontSize: 20,
                lineHeight: 1.6,
                color: toneColor[line.tone ?? 'plain'],
                whiteSpace: 'pre',
              }}
            >
              {line.text}
            </div>
          </Reveal>
        ))}
        {caption ? (
          <Reveal delay={startDelay + lines.length * lineStep + 8} y={10}>
            <div
              style={{
                marginTop: 14,
                fontSize: 19,
                color: COLORS.faint,
                lineHeight: 1.5,
              }}
            >
              {caption}
            </div>
          </Reveal>
        ) : null}
      </div>
    </div>
  );
};
