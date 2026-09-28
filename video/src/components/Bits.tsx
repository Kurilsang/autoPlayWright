import React from 'react';
import {COLORS} from '../theme';
import {Reveal} from './Reveal';

export type Tone = 'default' | 'good' | 'bad' | 'warn' | 'accent';

const TONE_COLOR: Record<Tone, string> = {
  default: COLORS.accent,
  good: COLORS.accent2,
  bad: COLORS.danger,
  warn: COLORS.warn,
  accent: COLORS.violet,
};

const MARKER: Record<Tone, string> = {
  default: '▸',
  good: '✓',
  bad: '✕',
  warn: '!',
  accent: '◆',
};

/** 项目列表（逐条浮入）。 */
export const BulletList: React.FC<{
  items: {text: string; sub?: string; tone?: Tone}[];
  startDelay?: number;
  step?: number;
  fontSize?: number;
  gap?: number;
}> = ({items, startDelay = 20, step = 26, fontSize = 29, gap = 22}) => {
  return (
    <div style={{display: 'flex', flexDirection: 'column', gap}}>
      {items.map((item, i) => {
        const tone: Tone = item.tone ?? 'default';
        return (
          <Reveal key={item.text} delay={startDelay + i * step} y={22}>
            <div style={{display: 'flex', gap: 16, alignItems: 'flex-start'}}>
              <div
                style={{
                  color: TONE_COLOR[tone],
                  fontSize: fontSize * 0.9,
                  fontWeight: 800,
                  lineHeight: 1.45,
                  width: 30,
                  flexShrink: 0,
                  textAlign: 'center',
                }}
              >
                {MARKER[tone]}
              </div>
              <div style={{flex: 1}}>
                <div
                  style={{
                    fontSize,
                    lineHeight: 1.5,
                    fontWeight: 650,
                    color: COLORS.text,
                  }}
                >
                  {item.text}
                </div>
                {item.sub ? (
                  <div
                    style={{
                      fontSize: fontSize * 0.82,
                      lineHeight: 1.5,
                      color: COLORS.dim,
                      marginTop: 4,
                    }}
                  >
                    {item.sub}
                  </div>
                ) : null}
              </div>
            </div>
          </Reveal>
        );
      })}
    </div>
  );
};

/** 标题 + 说明的小卡片。 */
export const Card: React.FC<{
  title: string;
  body: string;
  tone?: Tone;
  badge?: string;
  height?: number | string;
}> = ({title, body, tone = 'accent', badge, height}) => {
  return (
    <div
      style={{
        background: COLORS.panel,
        border: `1px solid ${COLORS.border}`,
        borderLeft: `5px solid ${TONE_COLOR[tone]}`,
        borderRadius: 16,
        padding: '24px 28px',
        height,
        boxSizing: 'border-box',
      }}
    >
      <div style={{display: 'flex', alignItems: 'center', gap: 12}}>
        {badge ? (
          <span
            style={{
              fontSize: 18,
              fontWeight: 800,
              color: TONE_COLOR[tone],
              background: 'rgba(255,255,255,0.06)',
              border: `1px solid ${COLORS.border}`,
              borderRadius: 8,
              padding: '3px 11px',
            }}
          >
            {badge}
          </span>
        ) : null}
        <div style={{fontSize: 28, fontWeight: 750, lineHeight: 1.35}}>
          {title}
        </div>
      </div>
      <div
        style={{
          marginTop: 12,
          fontSize: 22,
          lineHeight: 1.55,
          color: COLORS.dim,
        }}
      >
        {body}
      </div>
    </div>
  );
};

/** 一行胶囊标签。 */
export const Chip: React.FC<{
  label: string;
  tone?: Tone;
  fontSize?: number;
}> = ({label, tone = 'default', fontSize = 21}) => {
  return (
    <span
      style={{
        display: 'inline-block',
        fontSize,
        fontWeight: 650,
        color: COLORS.text,
        background: 'rgba(255,255,255,0.06)',
        border: `1px solid ${TONE_COLOR[tone]}55`,
        borderRadius: 999,
        padding: '8px 18px',
      }}
    >
      {label}
    </span>
  );
};
